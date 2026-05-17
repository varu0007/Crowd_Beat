"""
session.py — DJ Session 管理路由
端点：
  POST   /host/session            → 创建新 session
  GET    /host/session/{id}       → 查询 session 状态
  DELETE /host/session/{id}       → 关闭 session
"""

import io
import uuid
from datetime import datetime, timezone

import qrcode
import qrcode.constants
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import (
    get_db,
    Session as DBSession,
    Guest,
    Recommendation,
)
from app.services import crowd_engine

router = APIRouter(prefix="/host", tags=["session"])


# ── Request / Response Schemas ──

class SessionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="场次名称")
    genre_seeds: list[str] = Field(
        default=[],
        max_length=5,
        description="Cold start 预设流派 (最多5个)",
    )


class SessionResponse(BaseModel):
    session_id: str
    name: str
    status: str
    genre_seeds: list[str]
    guest_count: int
    ws_connections: int
    qr_url: str
    created_at: str

    model_config = {"from_attributes": True}


# ── Endpoints ──

@router.post("/session", response_model=SessionResponse)
async def create_session(
    req: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """DJ 创建新的活动场次"""
    new_session = DBSession(
        name=req.name,
        genre_seeds=req.genre_seeds,
        status="active",
    )
    db.add(new_session)
    await db.flush()

    settings = get_settings()
    qr_url = f"{settings.FRONTEND_URL}/join/{new_session.id}"

    return SessionResponse(
        session_id=str(new_session.id),
        name=new_session.name,
        status=new_session.status,
        genre_seeds=req.genre_seeds,
        guest_count=0,
        ws_connections=0,
        qr_url=qr_url,
        created_at=new_session.created_at.isoformat(),
    )


@router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """查询 session 状态"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    result = await db.execute(select(DBSession).where(DBSession.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 统计 guest 数量
    guest_count_result = await db.execute(
        select(func.count()).where(Guest.session_id == sid)
    )
    guest_count = guest_count_result.scalar() or 0

    settings = get_settings()
    qr_url = f"{settings.FRONTEND_URL}/join/{session_id}"

    return SessionResponse(
        session_id=str(session.id),
        name=session.name,
        status=session.status,
        genre_seeds=session.genre_seeds or [],
        guest_count=guest_count,
        ws_connections=crowd_engine.get_connection_count(sid),
        qr_url=qr_url,
        created_at=session.created_at.isoformat(),
    )


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """DJ 关闭 session（逻辑删除，更新状态为 closed）"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    result = await db.execute(select(DBSession).where(DBSession.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = "closed"
    session.closed_at = datetime.now(timezone.utc)
    await db.flush()

    # 通知 WebSocket 客户端 session 已关闭
    await crowd_engine.broadcast(sid, {
        "type": "session_closed",
        "session_id": session_id,
    })
    crowd_engine.close_session(sid)

    return {"detail": "Session closed", "session_id": session_id}


@router.get("/session/{session_id}/qr")
async def get_session_qr(session_id: str):
    """生成 QR 码图片（PNG），guest 扫码后跳转到 /auth/login"""
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    settings = get_settings()
    # QR 码内容指向后端 auth/login 端点
    join_url = f"{settings.FRONTEND_URL}/join/{session_id}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(join_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")
