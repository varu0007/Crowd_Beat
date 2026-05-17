"""CrowdBeat module."""

import json
import uuid
from typing import Any

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session_factory
from app.services import ml_engine


# ---
# ---
# ---

_connections: dict[uuid.UUID, set[WebSocket]] = {}


async def connect(session_id: uuid.UUID, websocket: WebSocket) -> None:
    """Internal helper."""
    await websocket.accept()
    if session_id not in _connections:
        _connections[session_id] = set()
    _connections[session_id].add(websocket)
    print(f"[crowd_engine] WS connected: session={session_id}, total={len(_connections[session_id])}")


async def disconnect(session_id: uuid.UUID, websocket: WebSocket) -> None:
    """Internal helper."""
    if session_id in _connections:
        _connections[session_id].discard(websocket)
        if not _connections[session_id]:
            del _connections[session_id]
    print(f"[crowd_engine] WS disconnected: session={session_id}")


async def broadcast(session_id: uuid.UUID, payload: dict[str, Any]) -> None:
    """Internal helper."""
    if session_id not in _connections:
        return

    message = json.dumps(payload, ensure_ascii=False, default=str)
    dead_sockets = set()

    for ws in _connections[session_id]:
        try:
            await ws.send_text(message)
        except Exception:
            dead_sockets.add(ws)

    # ---
    for ws in dead_sockets:
        _connections[session_id].discard(ws)


async def on_guest_join(
    session_id: uuid.UUID,
    guest_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """Internal helper."""
    print(f"[debug] on_guest_join called, session_id={session_id}")
    # ---
    recommendations = await ml_engine.recompute(session_id, db)

    # ---
    await broadcast(session_id, {
        "type": "recommendations_update",
        "session_id": str(session_id),
        "guest_id": str(guest_id),
        "recommendations": recommendations,
    })

    # ---
    await broadcast(session_id, {
        "type": "guest_joined",
        "session_id": str(session_id),
        "guest_id": str(guest_id),
    })

    return recommendations


async def notify_guest_tracks_shared(
    session_id: uuid.UUID,
    guest_id: uuid.UUID,
) -> None:
    """Notify dashboards that a guest shared tracks without blocking on ML."""
    await broadcast(session_id, {
        "type": "guest_joined",
        "session_id": str(session_id),
        "guest_id": str(guest_id),
    })


async def recompute_and_broadcast(
    session_id: uuid.UUID,
    guest_id: uuid.UUID,
) -> None:
    """Recompute recommendations in the background with its own DB session."""
    print(f"[debug] background recompute called, session_id={session_id}")
    factory = get_session_factory()
    async with factory() as db:
        try:
            recommendations = await ml_engine.recompute(session_id, db)
            await db.commit()
        except Exception as e:
            await db.rollback()
            print(f"[crowd_engine] background recompute failed: {e}")
            return

    await broadcast(session_id, {
        "type": "recommendations_update",
        "session_id": str(session_id),
        "guest_id": str(guest_id),
        "recommendations": recommendations,
    })


def close_session(session_id: uuid.UUID) -> None:
    """Internal helper."""
    if session_id in _connections:
        del _connections[session_id]


def get_connection_count(session_id: uuid.UUID) -> int:
    """Internal helper."""
    return len(_connections.get(session_id, set()))
