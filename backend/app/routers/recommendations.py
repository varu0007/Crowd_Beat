"""
recommendations.py — 推荐结果路由
端点：
  GET  /recommendations/{session_id}          → 获取当前推荐列表
  POST /recommendations/{session_id}/refresh  → 手动刷新推荐
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db, Recommendation, Session as DBSession
from app.services import ml_engine, crowd_engine

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


# ── Response Schemas ──

class RecommendationItem(BaseModel):
    spotify_track_id: str
    track_name: str | None
    artist_name: str | None
    score: float | None
    rank: int | None
    is_cold_start: bool

    model_config = {"from_attributes": True}


class RecommendationsResponse(BaseModel):
    session_id: str
    count: int
    guest_count: int | None
    is_cold_start: bool
    recommendations: list[RecommendationItem]


# ── Endpoints ──

@router.get("/{session_id}", response_model=RecommendationsResponse)
async def get_recommendations(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取指定 session 的当前推荐列表"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    # 验证 session 存在
    session_result = await db.execute(
        select(DBSession).where(DBSession.id == sid)
    )
    if not session_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    # 查询推荐
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.session_id == sid)
        .order_by(Recommendation.rank.asc())
    )
    recs = result.scalars().all()

    if not recs:
        return RecommendationsResponse(
            session_id=session_id,
            count=0,
            guest_count=0,
            is_cold_start=False,
            recommendations=[],
        )

    items = [
        RecommendationItem(
            spotify_track_id=r.spotify_track_id,
            track_name=r.track_name,
            artist_name=r.artist_name,
            score=r.score,
            rank=r.rank,
            is_cold_start=r.is_cold_start,
        )
        for r in recs
    ]

    return RecommendationsResponse(
        session_id=session_id,
        count=len(items),
        guest_count=recs[0].guest_count if recs else 0,
        is_cold_start=recs[0].is_cold_start if recs else False,
        recommendations=items,
    )


@router.post("/{session_id}/refresh", response_model=RecommendationsResponse)
async def refresh_recommendations(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """DJ 手动触发推荐刷新"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    # 验证 session 存在且活跃
    session_result = await db.execute(
        select(DBSession).where(
            DBSession.id == sid,
            DBSession.status == "active",
        )
    )
    if not session_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found or closed")

    # 重新计算推荐
    recommendations = await ml_engine.recompute(sid, db)

    # WebSocket 广播
    await crowd_engine.broadcast(sid, {
        "type": "recommendations_update",
        "session_id": session_id,
        "recommendations": recommendations,
    })

    is_cold = recommendations[0]["is_cold_start"] if recommendations else False

    items = [
        RecommendationItem(
            spotify_track_id=r["spotify_track_id"],
            track_name=r["track_name"],
            artist_name=r["artist_name"],
            score=r["score"],
            rank=r["rank"],
            is_cold_start=r.get("is_cold_start", False),
        )
        for r in recommendations
    ]

    return RecommendationsResponse(
        session_id=session_id,
        count=len(items),
        guest_count=0,
        is_cold_start=is_cold,
        recommendations=items,
    )
