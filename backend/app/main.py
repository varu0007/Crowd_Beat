"""
main.py — FastAPI 应用入口
职责：
  - 创建 FastAPI 实例
  - 注册路由 (auth, session, recommendations)
  - 配置 CORS
  - 注册 WebSocket 端点
  - 管理数据库生命周期
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models.database import init_db, close_db
from app.routers import auth, session, recommendations, guest, admin
from app.services import crowd_engine
from app.config import get_settings

# ── Lifespan ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动：初始化数据库表
    print("[CrowdBeat] Initializing database...")
    await init_db()
    print("[CrowdBeat] Database ready.")
    yield
    # 关闭：释放数据库连接池
    print("[CrowdBeat] Shutting down database...")
    await close_db()
    print("[CrowdBeat] Shutdown complete.")


# ── App ──

app = FastAPI(
    title="CrowdBeat API",
    description="实时音乐推荐系统 — DJ 用",
    version="0.1.0",
    lifespan=lifespan,
)


# ── CORS ──
# 延迟加载 settings，允许 .env 缺失时仍能导入模块
try:
    _settings = get_settings()
    _origins = [
        _settings.FRONTEND_URL,
        # Vite dev server defaults
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        # Jupyter / other dev hosts
        "http://localhost:8888",
        "http://127.0.0.1:8888",
        # Remote LAN host (used by you)
        "http://192.168.1.104:8888",
        "http://192.168.56.1:8888",
    ]
except Exception:
    _origins = [
        "http://localhost:5173", 
        "http://127.0.0.1:5173",
        "http://localhost:8888",
        "http://127.0.0.1:8888",
        "http://192.168.56.1:8888",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"^https://.*\.(vercel\.app|railway\.app|up\.railway\.app)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ──

app.include_router(auth.router)
app.include_router(session.router)
app.include_router(recommendations.router)
app.include_router(guest.router)
app.include_router(admin.router)


# ── WebSocket ──

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    DJ Dashboard WebSocket 端点
    连接后持续接收推荐更新
    """
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid session_id")
        return

    await crowd_engine.connect(sid, websocket)

    try:
        # 保持连接，等待客户端消息（ping/pong 或手动操作）
        while True:
            data = await websocket.receive_text()
            # 可扩展：处理客户端发来的指令
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await crowd_engine.disconnect(sid, websocket)
    except Exception:
        await crowd_engine.disconnect(sid, websocket)


# ── Health Check ──

@app.get("/health", tags=["system"])
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "service": "crowdbeat-api"}
