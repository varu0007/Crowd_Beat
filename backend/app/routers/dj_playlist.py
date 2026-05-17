"""
dj_playlist.py — DJ Spotify 歌单管理路由 (Virtual Playlist Version with DB)
端点：
  POST /host/session/{session_id}/playlist/create    → 创建虚拟歌单
  POST /host/session/{session_id}/playlist/add-track  → 添加歌曲到虚拟歌单
  GET  /host/session/{session_id}/playlist/tracks     → 获取虚拟歌单曲目列表
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db, Session as DBSession, PlaylistTrack

router = APIRouter(prefix="/host", tags=["dj_playlist"])


# ── Request Schemas ──

class CreatePlaylistRequest(BaseModel):
    playlist_name: str = Field(..., min_length=1, max_length=200, description="歌单名称")


class AddTrackRequest(BaseModel):
    track_id: str = Field(..., description="Spotify track ID")
    track_name: str = Field(default="Unknown Track", description="歌曲名称")
    artist_name: str = Field(default="Unknown Artist", description="歌手名称")


# ── 内存缓存：session_id -> 虚拟歌单名称 ──
# 歌曲本身存进数据库，但歌单名称存在 session 表里或者内存里（为了简单，先放内存，由于不重要，丢了也没事）
_session_playlist_names: dict[str, str] = {}


# ── Endpoints ──

@router.post("/session/{session_id}/playlist/create")
async def create_playlist(
    session_id: str,
    req: CreatePlaylistRequest,
    db: AsyncSession = Depends(get_db),
):
    """DJ 创建虚拟歌单（绕过 Spotify API 限制）"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    # 验证 session 存在
    result = await db.execute(select(DBSession).where(DBSession.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    playlist_url = f"crowdbeat://playlist/{session_id}"

    # 保存歌单名字到内存（也可以在 sessions 表加字段，这里求简）
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
    """将推荐歌曲添加到虚拟歌单（持久化到数据库）"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")


    # 检查是否重复
    existing = await db.execute(
        select(PlaylistTrack).where(
            PlaylistTrack.session_id == sid,
            PlaylistTrack.spotify_track_id == req.track_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Track already in playlist")

    # 添加到数据库
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
    """获取虚拟歌单中的曲目列表（持久化版本）"""
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

    playlist_name = _session_playlist_names.get(session_id, "内部歌单")

    return {
        "tracks": tracks,
        "playlist_url": f"crowdbeat://playlist/{session_id}",
        "playlist_name": playlist_name
    }

