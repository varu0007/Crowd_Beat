"""
main.py â€” FastAPI åº”ç”¨å…¥å£
èŒè´£ï¼š
  - åˆ›å»º FastAPI å®žä¾‹
  - æ³¨å†Œè·¯ç”± (auth, session, recommendations)
  - é…ç½® CORS
  - æ³¨å†Œ WebSocket ç«¯ç‚¹
  - ç®¡ç†æ•°æ®åº“ç”Ÿå‘½å‘¨æœŸ
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models.database import init_db, close_db
from app.routers import auth, session, recommendations, guest, admin, dj_playlist
from app.services import crowd_engine


# â”€â”€ Lifespan â”€â”€

@asynccontextmanager
async def lifespan(app: FastAPI):
    """åº”ç”¨ç”Ÿå‘½å‘¨æœŸç®¡ç†"""
    # å¯åŠ¨ï¼šåˆå§‹åŒ–æ•°æ®åº“è¡¨
    print("[CrowdBeat] Initializing database...")
    await init_db()
    print("[CrowdBeat] Database ready.")
    yield
    # å…³é—­ï¼šé‡Šæ”¾æ•°æ®åº“è¿žæŽ¥æ±
    print("[CrowdBeat] Shutting down database...")
    await close_db()
    print("[CrowdBeat] Shutdown complete.")


# â”€â”€ App â”€â”€

app = FastAPI(
    title="CrowdBeat API",
    description="å®žæ—¶éŸ³ä¹æŽ¨èç³»ç»Ÿ â€” DJ ç”¨",
    version="0.1.0",
    lifespan=lifespan,
)


# â”€â”€ CORS â”€â”€
# å»¶è¿ŸåŠ è½½ settingsï¼Œå…è®¸ .env ç¼ºå¤±æ—¶ä»èƒ½å¯¼å…¥æ¨¡å—
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


# â”€â”€ Routers â”€â”€

app.include_router(auth.router)
app.include_router(session.router)
app.include_router(recommendations.router)
app.include_router(guest.router)
app.include_router(admin.router)
app.include_router(dj_playlist.router)


# â”€â”€ WebSocket â”€â”€

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    DJ Dashboard WebSocket ç«¯ç‚¹
    è¿žæŽ¥åŽæŒç»­æŽ¥æ”¶æŽ¨èæ›´æ–°
    """
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid session_id")
        return

    await crowd_engine.connect(sid, websocket)

    try:
        # ä¿æŒè¿žæŽ¥ï¼Œç­‰å¾…å®¢æˆ·ç«¯æ¶ˆæ¯ï¼ˆping/pong æˆ–æ‰‹åŠ¨æ“ä½œï¼‰
        while True:
            data = await websocket.receive_text()
            # å¯æ‰©å±•ï¼šå¤„ç†å®¢æˆ·ç«¯å‘æ¥çš„æŒ‡ä»¤
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await crowd_engine.disconnect(sid, websocket)
    except Exception:
        await crowd_engine.disconnect(sid, websocket)


# â”€â”€ Health Check â”€â”€

@app.get("/health", tags=["system"])
async def health_check():
    """å¥åº·æ£€æŸ¥ç«¯ç‚¹"""
    return {"status": "ok", "service": "crowdbeat-api"}
