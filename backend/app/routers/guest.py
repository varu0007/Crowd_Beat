"""
guest.py — 观众相关端点
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db, Guest, GuestTrack
from app.services import spotify_service, crowd_engine

router = APIRouter(prefix="/guest", tags=["guest"])


class PlaylistSelection(BaseModel):
    playlist_ids: List[str]


class TrackSelection(BaseModel):
    tracks: List[dict]  # [{spotify_track_id, track_name, artist_name, playlist_name?}]


@router.get("/{guest_id}/playlists")
async def get_playlists(guest_id: str, db: AsyncSession = Depends(get_db)):
    try:
        gid = uuid.UUID(guest_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid guest_id")

    result = await db.execute(select(Guest).where(Guest.id == gid))
    guest = result.scalar_one_or_none()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    if not guest.access_token:
        raise HTTPException(status_code=400, detail="Guest has no access token")

    try:
        liked = await spotify_service.get_user_liked_songs(guest.access_token)
        normal_playlists = await spotify_service.get_user_playlists(guest.access_token, limit=50)
        playlists = [liked] + normal_playlists
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch playlists: {e}")

    return_playlists = {
        "guest_id": guest_id,
        "display_name": guest.display_name,
        "playlists": playlists,
    }
    return return_playlists


@router.post("/{guest_id}/playlists")
async def submit_playlists(
    guest_id: str,
    payload: PlaylistSelection,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    try:
        gid = uuid.UUID(guest_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid guest_id")

    if len(payload.playlist_ids) > 5:
        raise HTTPException(status_code=400, detail="Max 5 playlists allowed")

    result = await db.execute(select(Guest).where(Guest.id == gid))
    guest = result.scalar_one_or_none()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    if not guest.access_token:
        raise HTTPException(status_code=400, detail="Guest has no access token")

    # 1. Fetch all tracks for selected playlists
    all_tracks = []
    for pid in payload.playlist_ids:
        try:
            tracks = await spotify_service.get_playlist_tracks(guest.access_token, pid)
            all_tracks.extend(tracks)
        except Exception as e:
            print(f"[guest] Error fetching playlist {pid}: {e}")

    # 2. Deduplicate tracks
    unique_tracks = {}
    for t in all_tracks:
        unique_tracks[t["spotify_track_id"]] = t

    deduped_tracks = list(unique_tracks.values())
    if not deduped_tracks:
        return {"ok": True, "tracks_analyzed": 0}

    # 3. Fetch audio features in batches
    track_ids = [t["spotify_track_id"] for t in deduped_tracks]
    try:
        features_map = await spotify_service.get_audio_features_batch(guest.access_token, track_ids)
    except Exception as e:
        print(f"[guest] Error fetching audio features: {e}")
        features_map = {}

    # 4. Insert into GuestTrack
    for t in deduped_tracks:
        tid = t["spotify_track_id"]
        features = features_map.get(tid, {})
        print(f"[debug] track={t['track_name']}, popularity={t.get('popularity')}")
        guest_track = GuestTrack(
            guest_id=guest.id,
            spotify_track_id=tid,
            track_name=t["track_name"],
            artist_name=t["artist_name"],
            danceability=features.get("danceability"),
            energy=features.get("energy"),
            valence=features.get("valence"),
            tempo=features.get("tempo"),
            acousticness=features.get("acousticness"),
            instrumentalness=features.get("instrumentalness"),
            popularity=t.get("popularity"),
        )
        db.add(guest_track)

    await db.flush()
    await db.commit()

    # 5. Notify immediately, then generate recommendations after responding.
    await crowd_engine.notify_guest_tracks_shared(guest.session_id, guest.id)
    background_tasks.add_task(crowd_engine.recompute_and_broadcast, guest.session_id, guest.id)

    return {"ok": True, "tracks_analyzed": len(deduped_tracks)}


@router.get("/{guest_id}/playlists/{playlist_id}/tracks")
async def get_playlist_tracks(guest_id: str, playlist_id: str, db: AsyncSession = Depends(get_db)):
    """获取指定歌单内的歌曲列表"""
    try:
        gid = uuid.UUID(guest_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid guest_id")

    result = await db.execute(select(Guest).where(Guest.id == gid))
    guest = result.scalar_one_or_none()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    if not guest.access_token:
        raise HTTPException(status_code=400, detail="Guest has no access token")

    try:
        if playlist_id == "liked_songs":
            tracks = await spotify_service.get_user_liked_songs_tracks(guest.access_token)
        else:
            tracks = await spotify_service.get_playlist_tracks(guest.access_token, playlist_id)
    except Exception as e:
        error_str = str(e)
        if "403" in error_str or "Forbidden" in error_str:
            # 权限不足（如别人的歌单、受限歌单），返回空列表而不是报错
            print(f"[guest] 403 for playlist {playlist_id}: {e}")
            return {"playlist_id": playlist_id, "tracks": [], "error": "此歌单无法访问（权限不足）"}
        raise HTTPException(status_code=500, detail=f"Failed to fetch tracks: {e}")

    return {"playlist_id": playlist_id, "tracks": tracks}


@router.post("/{guest_id}/tracks")
async def submit_tracks(
    guest_id: str,
    payload: TrackSelection,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """提交用户选择的具体歌曲进行分析"""
    try:
        gid = uuid.UUID(guest_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid guest_id")

    result = await db.execute(select(Guest).where(Guest.id == gid))
    guest = result.scalar_one_or_none()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    if not guest.access_token:
        raise HTTPException(status_code=400, detail="Guest has no access token")

    if not payload.tracks:
        return {"ok": True, "tracks_analyzed": 0}

    # 1. Deduplicate tracks
    unique_tracks = {}
    for t in payload.tracks:
        unique_tracks[t["spotify_track_id"]] = t
    deduped_tracks = list(unique_tracks.values())

    # 2. Fetch audio features in batches
    track_ids = [t["spotify_track_id"] for t in deduped_tracks]
    try:
        features_map = await spotify_service.get_audio_features_batch(guest.access_token, track_ids)
    except Exception as e:
        print(f"[guest] Error fetching audio features: {e}")
        features_map = {}

    # 3. Insert into GuestTrack
    for t in deduped_tracks:
        tid = t["spotify_track_id"]
        features = features_map.get(tid, {})
        print(f"[debug] track={t.get('track_name', 'Unknown')}, popularity={t.get('popularity')}")
        guest_track = GuestTrack(
            guest_id=guest.id,
            spotify_track_id=tid,
            track_name=t.get("track_name", "Unknown"),
            artist_name=t.get("artist_name", "Unknown"),
            danceability=features.get("danceability"),
            energy=features.get("energy"),
            valence=features.get("valence"),
            tempo=features.get("tempo"),
            acousticness=features.get("acousticness"),
            instrumentalness=features.get("instrumentalness"),
            popularity=t.get("popularity", 0),
        )
        db.add(guest_track)

    await db.flush()
    await db.commit()

    # 4. Notify immediately, then generate recommendations after responding.
    await crowd_engine.notify_guest_tracks_shared(guest.session_id, guest.id)
    background_tasks.add_task(crowd_engine.recompute_and_broadcast, guest.session_id, guest.id)

    return {"ok": True, "tracks_analyzed": len(deduped_tracks)}
