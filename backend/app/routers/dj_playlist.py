"""
dj_playlist.py â€” DJ Spotify æ­Œå•ç®¡ç†è·¯ç”± (Virtual Playlist Version with DB)
ç«¯ç‚¹ï¼š
  POST /host/session/{session_id}/playlist/create    â†’ åˆ›å»ºè™šæ‹Ÿæ­Œå•
  POST /host/session/{session_id}/playlist/add-track  â†’ æ·»åŠ æ­Œæ›²åˆ°è™šæ‹Ÿæ­Œå•
  GET  /host/session/{session_id}/playlist/tracks     â†’ èŽ·å–è™šæ‹Ÿæ­Œå•æ›²ç›®åˆ—è¡¨
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db, Session as DBSession, PlaylistTrack

router = APIRouter(prefix="/host", tags=["dj_playlist"])


# â”€â”€ Request Schemas â”€â”€

class CreatePlaylistRequest(BaseModel):
    playlist_name: str = Field(..., min_length=1, max_length=200, description="æ­Œå•åç§°")


class AddTrackRequest(BaseModel):
    track_id: str = Field(..., description="Spotify track ID")
    track_name: str = Field(default="Unknown Track", description="æ­Œæ›²åç§°")
    artist_name: str = Field(default="Unknown Artist", description="æ­Œæ‰‹åç§°")


# â”€â”€ å†…å­˜ç¼“å­˜ï¼šsession_id -> è™šæ‹Ÿæ­Œå•åç§° â”€â”€
# æ­Œæ›²æœ¬èº«å­˜è¿›æ•°æ®åº“ï¼Œä½†æ­Œå•åç§°å­˜åœ¨ session è¡¨é‡Œæˆ–è€…å†…å­˜é‡Œï¼ˆä¸ºäº†ç®€å•ï¼Œå…ˆæ”¾å†…å­˜ï¼Œç”±äºŽä¸é‡è¦ï¼Œä¸¢äº†ä¹Ÿæ²¡äº‹ï¼‰
_session_playlist_names: dict[str, str] = {}
_session_dj_tokens: dict[str, str] = {}


# â”€â”€ Endpoints â”€â”€

@router.post("/session/{session_id}/playlist/create")
async def create_playlist(
    session_id: str,
    req: CreatePlaylistRequest,
    db: AsyncSession = Depends(get_db),
):
    """DJ åˆ›å»ºè™šæ‹Ÿæ­Œå•ï¼ˆç»•è¿‡ Spotify API é™åˆ¶ï¼‰"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    # éªŒè¯ session å­˜åœ¨
    result = await db.execute(select(DBSession).where(DBSession.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    playlist_url = f"crowdbeat://playlist/{session_id}"

    # ä¿å­˜æ­Œå•åå­—åˆ°å†…å­˜ï¼ˆä¹Ÿå¯ä»¥åœ¨ sessions è¡¨åŠ å­—æ®µï¼Œè¿™é‡Œæ±‚ç®€ï¼‰
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
    """å°†æŽ¨èæ­Œæ›²æ·»åŠ åˆ°è™šæ‹Ÿæ­Œå•ï¼ˆæŒä¹…åŒ–åˆ°æ•°æ®åº“ï¼‰"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")


    # æ£€æŸ¥æ˜¯å¦é‡å¤
    existing = await db.execute(
        select(PlaylistTrack).where(
            PlaylistTrack.session_id == sid,
            PlaylistTrack.spotify_track_id == req.track_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Track already in playlist")

    # æ·»åŠ åˆ°æ•°æ®åº“
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
    """èŽ·å–è™šæ‹Ÿæ­Œå•ä¸­çš„æ›²ç›®åˆ—è¡¨ï¼ˆæŒä¹…åŒ–ç‰ˆæœ¬ï¼‰"""
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

    playlist_name = _session_playlist_names.get(session_id, "å†…éƒ¨æ­Œå•")

    return {
        "tracks": tracks,
        "playlist_url": f"crowdbeat://playlist/{session_id}",
        "playlist_name": playlist_name
    }
