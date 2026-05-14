"""Internal helper."""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from app.config import get_settings


def _get_oauth_manager() -> SpotifyOAuth:
    """åˆ›å»º SpotifyOAuth ç®¡ç†å™¨ï¼ˆAuthorization Code Flowï¼Œéž PKCEï¼‰"""
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
    ç”Ÿæˆ Spotify æŽˆæƒ URL
    å°† session_id ç¼–ç è¿› state å‚æ•°ï¼Œå›žè°ƒæ—¶å¯æ¢å¤
    """
    oauth = _get_oauth_manager()
    return oauth.get_authorize_url(state=session_id)


async def exchange_token(code: str) -> dict:
    """
    ç”¨ authorization code æ¢å– access_token
    è¿”å›ž: {access_token, refresh_token, expires_at, expires_in}
    """
    oauth = _get_oauth_manager()
    # spotipy çš„ get_access_token æ˜¯åŒæ­¥çš„ï¼Œæ”¾åˆ°çº¿ç¨‹æ± æ‰§è¡Œ
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
    èŽ·å–å½“å‰ç”¨æˆ·ä¿¡æ¯
    è¿”å›ž: {spotify_user_id, display_name}
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
    èŽ·å–ç”¨æˆ· top tracks
    time_range: short_term (4å‘¨), medium_term (6ä¸ªæœˆ), long_term (å…¨éƒ¨)
    è¿”å›ž: [{spotify_track_id, track_name, artist_name, popularity}]
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
    æ‰¹é‡èŽ·å– audio featuresï¼ˆæ¯æ¬¡æœ€å¤š 100 ä¸ª IDï¼‰
    è¿”å›ž: {track_id: {danceability, energy, valence, tempo, acousticness, instrumentalness}}
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
            # Audio Features API å¯èƒ½å·²å¼ƒç”¨æˆ–æƒé™ä¸è¶³ï¼Œé™é»˜è·³è¿‡
            print(f"[spotify_service] audio_features error: {e}")
            continue

        # Rate limit ä¿æŠ¤
        if i + batch_size < len(track_ids):
            await asyncio.sleep(0.1)

    return features_map


async def get_recommendations_by_seeds(
    access_token: str,
    seed_genres: list[str] = None,
    seed_tracks: list[str] = None,
    limit: int = 20,
) -> list[dict]:
    """
    Cold start fallbackï¼šé€šè¿‡ genre/track seed èŽ·å– Spotify æŽ¨è
    è¿”å›ž: [{spotify_track_id, track_name, artist_name, popularity}]
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    kwargs = {"limit": limit}
    if seed_genres:
        kwargs["seed_genres"] = seed_genres[:5]  # Spotify æœ€å¤š 5 ä¸ª seed
    if seed_tracks:
        kwargs["seed_tracks"] = seed_tracks[:5]

    try:
        results = await loop.run_in_executor(
            None, lambda: sp.recommendations(**kwargs)
        )
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
    èŽ·å–ç”¨æˆ·çš„æ’­æ”¾åˆ—è¡¨
    è¿”å›ž: [{id, name, description, track_count, image_url, owner_name}]
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
    èŽ·å–ç”¨æˆ·çš„ Liked Songsï¼ˆæ”¶è—æ­Œæ›²ï¼‰
    è°ƒç”¨ GET /v1/me/tracks?limit=50
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
        "description": "ä½ æ”¶è—çš„æ­Œæ›²",
        "track_count": track_count,
        "image_url": None,
        "owner_name": "Spotify"
    }


async def get_user_liked_songs_tracks(access_token: str, limit: int = 50) -> list[dict]:
    """
    èŽ·å–ç”¨æˆ·çš„ Liked Songs æ­Œæ›²åˆ—è¡¨
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
    èŽ·å–æŒ‡å®šæ­Œå•å†…çš„æ›²ç›®
    è¿”å›ž: [{spotify_track_id, track_name, artist_name, album_name, popularity}]
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None, lambda: sp.playlist_tracks(playlist_id, limit=limit)
    )

    tracks = []
    for item in results.get("items", []):
        # Spotify API å¯èƒ½ç”¨ 'track' æˆ– 'item' ä½œä¸º key
        track_obj = item.get("track") or item.get("item")
        # è¿‡æ»¤æŽ‰ null æˆ–è€…æ˜¯ episode
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
