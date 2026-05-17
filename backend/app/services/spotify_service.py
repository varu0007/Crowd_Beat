"""
spotify_service.py — Spotify Web API 封装
职责：Token 交换、获取用户 top tracks、批量获取 audio features
使用 spotipy 库作为底层客户端
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from app.config import get_settings


def _get_oauth_manager() -> SpotifyOAuth:
    """创建 SpotifyOAuth 管理器（Authorization Code Flow，非 PKCE）"""
    settings = get_settings()
    return SpotifyOAuth(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        scope="user-top-read user-library-read playlist-read-private playlist-read-collaborative",
        show_dialog=True,
        open_browser=False,
    )


def get_authorize_url(session_id: str) -> str:
    """
    生成 Spotify 授权 URL
    将 session_id 编码进 state 参数，回调时可恢复
    """
    oauth = _get_oauth_manager()
    return oauth.get_authorize_url(state=session_id)


async def exchange_token(code: str) -> dict:
    """
    用 authorization code 换取 access_token
    返回: {access_token, refresh_token, expires_at, expires_in}
    """
    oauth = _get_oauth_manager()
    # spotipy 的 get_access_token 是同步的，放到线程池执行
    loop = asyncio.get_event_loop()
    token_info = await loop.run_in_executor(
        None, lambda: oauth.get_access_token(code, as_dict=True, check_cache=False)
    )
    return {
        "access_token": token_info["access_token"],
        "refresh_token": token_info.get("refresh_token", ""),
        "expires_in": token_info.get("expires_in", 3600),
        "expires_at": datetime.now(timezone.utc) + timedelta(
            seconds=token_info.get("expires_in", 3600)
        ),
    }


async def get_current_user(access_token: str) -> dict:
    """
    获取当前用户信息
    返回: {spotify_user_id, display_name}
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()
    user = await loop.run_in_executor(None, sp.current_user)
    return {
        "spotify_user_id": user.get("id", ""),
        "display_name": user.get("display_name", ""),
    }


async def get_user_top_tracks(
    access_token: str,
    limit: int = 50,
    time_range: str = "medium_term",
) -> list[dict]:
    """
    获取用户 top tracks
    time_range: short_term (4周), medium_term (6个月), long_term (全部)
    返回: [{spotify_track_id, track_name, artist_name, popularity}]
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None,
        lambda: sp.current_user_top_tracks(limit=limit, time_range=time_range),
    )

    tracks = []
    for item in results.get("items", []):
        tracks.append({
            "spotify_track_id": item["id"],
            "track_name": item.get("name", "Unknown"),
            "artist_name": ", ".join(a["name"] for a in item.get("artists", [])),
            "popularity": item.get("popularity", 0),
        })
    return tracks


async def get_audio_features_batch(
    access_token: str,
    track_ids: list[str],
) -> dict[str, dict]:
    """
    批量获取 audio features（每次最多 100 个 ID）
    返回: {track_id: {danceability, energy, valence, tempo, acousticness, instrumentalness}}
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()
    features_map: dict[str, dict] = {}
    batch_size = 100

    for i in range(0, len(track_ids), batch_size):
        batch = track_ids[i : i + batch_size]
        try:
            results = await loop.run_in_executor(
                None, lambda b=batch: sp.audio_features(tracks=b)
            )
            if results:
                for af in results:
                    if af and af.get("id"):
                        features_map[af["id"]] = {
                            "danceability": af.get("danceability"),
                            "energy": af.get("energy"),
                            "valence": af.get("valence"),
                            "tempo": af.get("tempo"),
                            "acousticness": af.get("acousticness"),
                            "instrumentalness": af.get("instrumentalness"),
                        }
        except Exception as e:
            # Audio Features API 可能已弃用或权限不足，静默跳过
            print(f"[spotify_service] audio_features error: {e}")
            continue

        # Rate limit 保护
        if i + batch_size < len(track_ids):
            await asyncio.sleep(0.1)

    return features_map


async def get_recommendations_by_seeds(
    access_token: str,
    seed_genres: list[str] = None,
    seed_tracks: list[str] = None,
    limit: int = 20,
    target_features: dict = None,
) -> list[dict]:
    """
    Content-based recommendations via Spotify API.
    target_features: {danceability, energy, valence, tempo, acousticness, instrumentalness}
    Returns: [{spotify_track_id, track_name, artist_name, popularity}]
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    kwargs = {"limit": limit}
    if seed_genres:
        kwargs["seed_genres"] = seed_genres[:5]
    if seed_tracks:
        kwargs["seed_tracks"] = seed_tracks[:5]
    if target_features:
        for key, val in target_features.items():
            if val is not None:
                kwargs[f"target_{key}"] = round(float(val), 4)

    try:
        results = await loop.run_in_executor(None, lambda: sp.recommendations(**kwargs))
    except Exception as e:
        print(f"[spotify_service] recommendations error: {e}")
        return []

    tracks = []
    for item in results.get("tracks", []):
        tracks.append({
            "spotify_track_id": item["id"],
            "track_name": item.get("name", "Unknown"),
            "artist_name": ", ".join(a["name"] for a in item.get("artists", [])),
            "popularity": item.get("popularity", 0),
        })
    return tracks


async def get_user_playlists(access_token: str, limit: int = 50) -> list[dict]:
    """
    获取用户的播放列表
    返回: [{id, name, description, track_count, image_url, owner_name}]
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None, lambda: sp.current_user_playlists(limit=limit)
    )

    playlists = []
    for item in results.get("items", []):
        image_url = item["images"][0]["url"] if item.get("images") else None
        playlists.append({
            "id": item["id"],
            "name": item.get("name", "Unknown"),
            "description": item.get("description", ""),
            "track_count": item.get("tracks", {}).get("total", 0),
            "image_url": image_url,
            "owner_name": item.get("owner", {}).get("display_name", "Unknown"),
        })
    return playlists


async def get_user_liked_songs(access_token: str, limit: int = 50) -> dict:
    """
    获取用户的 Liked Songs（收藏歌曲）
    调用 GET /v1/me/tracks?limit=50
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None, lambda: sp.current_user_saved_tracks(limit=limit)
    )

    track_count = results.get("total", 0)

    return {
        "id": "liked_songs",
        "name": "Liked Songs",
        "description": "你收藏的歌曲",
        "track_count": track_count,
        "image_url": None,
        "owner_name": "Spotify"
    }


async def get_user_liked_songs_tracks(access_token: str, limit: int = 50) -> list[dict]:
    """
    获取用户的 Liked Songs 歌曲列表
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None, lambda: sp.current_user_saved_tracks(limit=limit)
    )

    tracks = []
    for item in results.get("items", []):
        track_obj = item.get("track")
        if not track_obj or track_obj.get("type") != "track":
            continue

        album_name = track_obj.get("album", {}).get("name", "Unknown")
        artists = ", ".join(a.get("name", "") for a in track_obj.get("artists", []))

        tracks.append({
            "spotify_track_id": track_obj["id"],
            "track_name": track_obj.get("name", "Unknown"),
            "artist_name": artists,
            "album_name": album_name,
            "popularity": track_obj.get("popularity", 0),
        })
    return tracks


async def get_playlist_tracks(access_token: str, playlist_id: str, limit: int = 100) -> list[dict]:
    """
    获取指定歌单内的曲目
    返回: [{spotify_track_id, track_name, artist_name, album_name, popularity}]
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None, lambda: sp.playlist_tracks(playlist_id, limit=limit)
    )

    tracks = []
    for item in results.get("items", []):
        # Spotify API 可能用 'track' 或 'item' 作为 key
        track_obj = item.get("track") or item.get("item")
        # 过滤掉 null 或者是 episode
        if not track_obj or track_obj.get("type") != "track":
            continue
            
        album_name = track_obj.get("album", {}).get("name", "Unknown")
        artists = ", ".join(a.get("name", "") for a in track_obj.get("artists", []))
        
        tracks.append({
            "spotify_track_id": track_obj["id"],
            "track_name": track_obj.get("name", "Unknown"),
            "artist_name": artists,
            "album_name": album_name,
            "popularity": track_obj.get("popularity", 0),
        })
    return tracks
