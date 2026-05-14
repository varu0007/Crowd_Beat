"""CrowdBeat module."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (
    get_db,
    Session as DBSession,
    Guest,
    GuestTrack,
    Recommendation,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---

@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    """Internal helper."""
    result = await db.execute(
        select(DBSession).order_by(DBSession.created_at.desc()).limit(50)
    )
    sessions = result.scalars().all()

    items = []
    for s in sessions:
        # ---
        gc_result = await db.execute(
            select(func.count()).where(Guest.session_id == s.id)
        )
        guest_count = gc_result.scalar() or 0

        items.append({
            "id": str(s.id),
            "name": s.name,
            "host_spotify_id": s.host_spotify_id,
            "genre_seeds": s.genre_seeds or [],
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "closed_at": s.closed_at.isoformat() if s.closed_at else None,
            "guest_count": guest_count,
        })
    return items


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Internal helper."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    # ---
    guest_result = await db.execute(
        select(Guest.id).where(Guest.session_id == sid)
    )
    guest_ids = [row[0] for row in guest_result.all()]

    # ---
    await db.execute(
        delete(Recommendation).where(Recommendation.session_id == sid)
    )

    # ---
    if guest_ids:
        await db.execute(
            delete(GuestTrack).where(GuestTrack.guest_id.in_(guest_ids))
        )

    # ---
    await db.execute(
        delete(Guest).where(Guest.session_id == sid)
    )

    # ---
    await db.execute(
        delete(DBSession).where(DBSession.id == sid)
    )

    return {"ok": True}


# ---

@router.get("/guests")
async def list_guests(
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Internal helper."""
    stmt = select(Guest).order_by(Guest.joined_at.desc()).limit(100)

    if session_id:
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id")
        stmt = stmt.where(Guest.session_id == sid)

    result = await db.execute(stmt)
    guests = result.scalars().all()

    return [
        {
            "id": str(g.id),
            "session_id": str(g.session_id),
            "spotify_user_id": g.spotify_user_id,
            "display_name": g.display_name,
            "joined_at": g.joined_at.isoformat() if g.joined_at else None,
        }
        for g in guests
    ]


@router.delete("/guests/{guest_id}")
async def delete_guest(guest_id: str, db: AsyncSession = Depends(get_db)):
    """Internal helper."""
    try:
        gid = uuid.UUID(guest_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid guest_id")

    # ---
    await db.execute(
        delete(GuestTrack).where(GuestTrack.guest_id == gid)
    )

    # ---
    await db.execute(
        delete(Guest).where(Guest.id == gid)
    )

    return {"ok": True}


# ---

@router.get("/tracks")
async def list_tracks(
    guest_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Internal helper."""
    stmt = select(GuestTrack)

    if session_id:
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id")
        stmt = stmt.join(Guest, GuestTrack.guest_id == Guest.id).where(Guest.session_id == sid)

    if guest_id:
        try:
            gid = uuid.UUID(guest_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid guest_id")
        stmt = stmt.where(GuestTrack.guest_id == gid)

    stmt = stmt.order_by(GuestTrack.id.desc()).limit(200)

    result = await db.execute(stmt)
    tracks = result.scalars().all()

    return [
        {
            "id": t.id,
            "guest_id": str(t.guest_id),
            "spotify_track_id": t.spotify_track_id,
            "track_name": t.track_name,
            "artist_name": t.artist_name,
            "danceability": t.danceability,
            "energy": t.energy,
            "valence": t.valence,
            "tempo": t.tempo,
            "acousticness": t.acousticness,
            "instrumentalness": t.instrumentalness,
            "popularity": t.popularity,
        }
        for t in tracks
    ]


@router.delete("/tracks/{track_id}")
async def delete_track(track_id: int, db: AsyncSession = Depends(get_db)):
    """Internal helper."""
    await db.execute(
        delete(GuestTrack).where(GuestTrack.id == track_id)
    )
    return {"ok": True}


# ---

@router.get("/recommendations")
async def list_recommendations(
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Internal helper."""
    stmt = select(Recommendation).order_by(Recommendation.rank.asc()).limit(100)

    if session_id:
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id")
        stmt = stmt.where(Recommendation.session_id == sid)

    result = await db.execute(stmt)
    recs = result.scalars().all()

    return [
        {
            "id": r.id,
            "session_id": str(r.session_id),
            "spotify_track_id": r.spotify_track_id,
            "track_name": r.track_name,
            "artist_name": r.artist_name,
            "score": r.score,
            "rank": r.rank,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            "guest_count": r.guest_count,
            "is_cold_start": r.is_cold_start,
        }
        for r in recs
    ]

# ---

@router.get("/playlist_tracks")
async def list_playlist_tracks(
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Internal helper."""
    from app.models.database import PlaylistTrack
    stmt = select(PlaylistTrack).order_by(PlaylistTrack.added_at.desc()).limit(100)

    if session_id:
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id")
        stmt = stmt.where(PlaylistTrack.session_id == sid)

    result = await db.execute(stmt)
    tracks = result.scalars().all()

    return [
        {
            "id": t.id,
            "session_id": str(t.session_id),
            "spotify_track_id": t.spotify_track_id,
            "track_name": t.track_name,
            "artist_name": t.artist_name,
            "added_at": t.added_at.isoformat() if t.added_at else None,
        }
        for t in tracks
    ]
