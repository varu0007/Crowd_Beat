"""
FastAPI entrypoint for CrowdBeat.
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models.database import init_db, close_db
from app.routers import auth, session, recommendations, guest, admin, dj_playlist
from app.services import crowd_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and close shared application resources."""
    print("[CrowdBeat] Initializing database...")
    await init_db()
    print("[CrowdBeat] Database ready.")
    yield
    print("[CrowdBeat] Shutting down database...")
    await close_db()
    print("[CrowdBeat] Shutdown complete.")


app = FastAPI(
    title="CrowdBeat API",
    description="Real-time music recommendation system for DJs",
    version="0.1.0",
    lifespan=lifespan,
)


try:
    _settings = get_settings()
    _origins = [
        _settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8888",
        "http://127.0.0.1:8888",
    ]
except Exception:
    _origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8888",
        "http://127.0.0.1:8888",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"^https://.*\.(vercel\.app|railway\.app|up\.railway\.app)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(session.router)
app.include_router(recommendations.router)
app.include_router(guest.router)
app.include_router(admin.router)
app.include_router(dj_playlist.router)


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for live DJ dashboard updates."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid session_id")
        return

    await crowd_engine.connect(sid, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await crowd_engine.disconnect(sid, websocket)
    except Exception:
        await crowd_engine.disconnect(sid, websocket)


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "crowdbeat-api"}
