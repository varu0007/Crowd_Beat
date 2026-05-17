"""CrowdBeat module."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db, Recommendation, Session as DBSession
from app.services import ml_engine, crowd_engine

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


# ---

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


# ---

@router.get("/{session_id}", response_model=RecommendationsResponse)
async def get_recommendations(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Internal helper."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    # ---
    session_result = await db.execute(
        select(DBSession).where(DBSession.id == sid)
    )
    db_session = session_result.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    # ---
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.session_id == sid)
        .order_by(Recommendation.rank.asc())
    )
    recs = result.scalars().all()

    if not recs and db_session.status == "active":
        try:
            generated = await ml_engine.recompute(sid, db)
        except Exception as exc:
            print(f"[recommendations] lazy recompute failed: {exc}")
            generated = []

        if generated:
            items = [
                RecommendationItem(
                    spotify_track_id=r["spotify_track_id"],
                    track_name=r["track_name"],
                    artist_name=r["artist_name"],
                    score=r["score"],
                    rank=r["rank"],
                    is_cold_start=r.get("is_cold_start", False),
                )
                for r in generated
            ]
            guest_count_result = await db.execute(text(
                "SELECT COUNT(DISTINCT id) as cnt FROM guests WHERE session_id = :session_id"
            ), {"session_id": sid})
            real_guest_count = guest_count_result.scalar() or 0
            return RecommendationsResponse(
                session_id=session_id,
                count=len(items),
                guest_count=real_guest_count,
                is_cold_start=items[0].is_cold_start if items else False,
                recommendations=items,
            )

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

    # ---
    guest_count_result = await db.execute(text(
        "SELECT COUNT(DISTINCT id) as cnt FROM guests WHERE session_id = :session_id"
    ), {"session_id": sid})
    real_guest_count = guest_count_result.scalar() or 0

    return RecommendationsResponse(
        session_id=session_id,
        count=len(items),
        guest_count=real_guest_count,
        is_cold_start=recs[0].is_cold_start if recs else False,
        recommendations=items,
    )


@router.post("/{session_id}/refresh", response_model=RecommendationsResponse)
async def refresh_recommendations(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Internal helper."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    # ---
    session_result = await db.execute(
        select(DBSession).where(
            DBSession.id == sid,
            DBSession.status == "active",
        )
    )
    if not session_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found or closed")

    # ---
    try:
        recommendations = await ml_engine.recompute(sid, db)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # ---
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

    # ---
    guest_count_result = await db.execute(text(
        "SELECT COUNT(DISTINCT id) as cnt FROM guests WHERE session_id = :session_id"
    ), {"session_id": sid})
    real_guest_count = guest_count_result.scalar() or 0

    return RecommendationsResponse(
        session_id=session_id,
        count=len(items),
        guest_count=real_guest_count,
        is_cold_start=is_cold,
        recommendations=items,
    )
