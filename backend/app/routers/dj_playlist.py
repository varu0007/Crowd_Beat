"""
dj_playlist.py - DJ virtual playlist management routes (DB-backed)

Endpoints:
  POST /host/session/{session_id}/playlist/create    -> Create virtual playlist
  POST /host/session/{session_id}/playlist/add-track -> Add track to virtual playlist
  GET  /host/session/{session_id}/playlist/tracks    -> Get virtual playlist tracks
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db, Session as DBSession, PlaylistTrack

router = APIRouter(prefix="/host", tags=["dj_playlist"])


# -- Request Schemas --

class CreatePlaylistRequest(BaseModel):
    playlist_name: str = Field(..., min_length=1, max_length=200, description="Playlist name")


class AddTrackRequest(BaseModel):
    track_id: str = Field(..., description="Spotify track ID")
    track_name: str = Field(default="Unknown Track", description="Track name")
    artist_name: str = Field(default="Unknown Artist", description="Artist name")


# In-memory cache: session_id -> playlist name
# Tracks are stored in DB; playlist name is kept in memory for simplicity
_session_playlist_names: dict[str, str] = {}

# In-memory DJ token cache: session_id -> access_token
# auth.py DJ OAuth callback writes here, ml_engine.py reads for Spotify recommendations API
_session_dj_tokens: dict[str, str] = {}


# -- Endpoints --

@router.post("/session/{session_id}/playlist/create")
async def create_playlist(
    session_id: str,
    req: CreatePlaylistRequest,
    db: AsyncSession = Depends(get_db),
):
    """DJ creates a virtual playlist (bypasses Spotify API restrictions)."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    # Verify session exists
    result = await db.execute(select(DBSession).where(DBSession.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    playlist_url = f"crowdbeat://playlist/{session_id}"

    _session_playlist_names[session_id] = req.playlist_name

    return {
        "playlist_id": session_id,
        "playlist_url": playlist_url,
        "playlist_name": req.playlist_name,
    }


@router.post("/session/{session_id}/playlist/add-track")
async def add_track_to_playlist(
    session_id: str,
    req: AddTrackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add a recommended track to the virtual playlist (persisted to DB)."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    # Check for duplicates
    existing = await db.execute(
        select(PlaylistTrack).where(
            PlaylistTrack.session_id == sid,
            PlaylistTrack.spotify_track_id == req.track_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Track already in playlist")

    # Add to DB
    new_track = PlaylistTrack(
        session_id=sid,
        spotify_track_id=req.track_id,
        track_name=req.track_name,
        artist_name=req.artist_name,
    )
    db.add(new_track)
    await db.commit()

    return {"detail": "Track added to virtual playlist", "track_id": req.track_id, "playlist_id": session_id}


@router.get("/session/{session_id}/playlist/tracks")
async def get_playlist_tracks(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get the track list for the virtual playlist."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    result = await db.execute(
        select(PlaylistTrack).where(PlaylistTrack.session_id == sid).order_by(PlaylistTrack.added_at)
    )
    db_tracks = result.scalars().all()

    tracks = [
        {
            "spotify_track_id": t.spotify_track_id,
            "track_name": t.track_name,
            "artist_name": t.artist_name,
        }
        for t in db_tracks
    ]

    playlist_name = _session_playlist_names.get(session_id, "CrowdBeat Playlist")

    return {
        "tracks": tracks,
        "playlist_url": f"crowdbeat://playlist/{session_id}",
        "playlist_name": playlist_name
    }
