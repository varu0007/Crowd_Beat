"""
crowd_engine.py — Session 状态管理 + WebSocket 广播
职责：
  - 管理每个 session 的 WebSocket 连接池
  - guest 加入时触发推荐重算 + 广播
"""

import json
import uuid
from typing import Any

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import ml_engine


# ────────────────────────────────────────────
# 内存连接池: session_id → set[WebSocket]
# ────────────────────────────────────────────

_connections: dict[uuid.UUID, set[WebSocket]] = {}


async def connect(session_id: uuid.UUID, websocket: WebSocket) -> None:
    """DJ dashboard 连接 WebSocket"""
    await websocket.accept()
    if session_id not in _connections:
        _connections[session_id] = set()
    _connections[session_id].add(websocket)
    print(f"[crowd_engine] WS connected: session={session_id}, total={len(_connections[session_id])}")


async def disconnect(session_id: uuid.UUID, websocket: WebSocket) -> None:
    """断开 WebSocket"""
    if session_id in _connections:
        _connections[session_id].discard(websocket)
        if not _connections[session_id]:
            del _connections[session_id]
    print(f"[crowd_engine] WS disconnected: session={session_id}")


async def broadcast(session_id: uuid.UUID, payload: dict[str, Any]) -> None:
    """向指定 session 的所有 WebSocket 广播 JSON 消息"""
    if session_id not in _connections:
        return

    message = json.dumps(payload, ensure_ascii=False, default=str)
    dead_sockets = set()

    for ws in _connections[session_id]:
        try:
            await ws.send_text(message)
        except Exception:
            dead_sockets.add(ws)

    # 清理已断开的连接
    for ws in dead_sockets:
        _connections[session_id].discard(ws)


async def on_guest_join(
    session_id: uuid.UUID,
    guest_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """
    Guest 加入后触发：
    1. 重新计算推荐
    2. 向 DJ dashboard 广播更新
    """
    print(f"[debug] on_guest_join called, session_id={session_id}")
    # 重新计算推荐
    recommendations = await ml_engine.recompute(session_id, db)

    # 广播给 DJ
    await broadcast(session_id, {
        "type": "recommendations_update",
        "session_id": str(session_id),
        "guest_id": str(guest_id),
        "recommendations": recommendations,
    })

    # 广播 guest 加入通知
    await broadcast(session_id, {
        "type": "guest_joined",
        "session_id": str(session_id),
        "guest_id": str(guest_id),
    })

    return recommendations


def close_session(session_id: uuid.UUID) -> None:
    """关闭 session 时清理所有连接"""
    if session_id in _connections:
        del _connections[session_id]


def get_connection_count(session_id: uuid.UUID) -> int:
    """获取 session 的活跃 WebSocket 连接数"""
    return len(_connections.get(session_id, set()))
