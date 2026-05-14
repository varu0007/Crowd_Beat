"""
auth.py â€” Spotify OAuth è·¯ç”±
ç«¯ç‚¹ï¼š
  GET  /auth/login       â†’ ç”Ÿæˆ Spotify æŽˆæƒ URL
  GET  /auth/callback    â†’ æŽ¥æ”¶å›žè°ƒï¼Œæ¢å– tokenï¼ŒèŽ·å– top tracks + audio features
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import get_db, Guest, GuestTrack, Session as DBSession
from app.services import spotify_service, crowd_engine
from spotipy.oauth2 import SpotifyOAuth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(session_id: str = Query(..., description="DJ session ID to join")):
    """
    Guest æ‰«ç åŽè·³è½¬åˆ°æ­¤ç«¯ç‚¹
    ç”Ÿæˆ Spotify æŽˆæƒ URLï¼Œå°† session_id ç¼–ç åœ¨ state å‚æ•°ä¸­
    """
    # éªŒè¯ session_id æ ¼å¼
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    authorize_url = spotify_service.get_authorize_url(session_id=session_id)
    return RedirectResponse(url=authorize_url)


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Spotify OAuth å›žè°ƒ

    æµç¨‹ï¼š
    1. ç”¨ code æ¢å– access_token
    2. èŽ·å–ç”¨æˆ·ä¿¡æ¯
    3. èŽ·å– top tracks
    4. èŽ·å– audio features
    5. å­˜å…¥æ•°æ®åº“
    6. è§¦å‘æŽ¨èé‡ç®— + WebSocket å¹¿æ’­
    7. é‡å®šå‘åˆ°å‰ç«¯æˆåŠŸé¡µ
    """
    settings = get_settings()

    # ä»Ž state æ¢å¤ session_id
    session_id_str = state
    try:
        session_id = uuid.UUID(session_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state (session_id)")

    # éªŒè¯ session å­˜åœ¨ä¸”æ´»è·ƒ
    session_result = await db.execute(
        select(DBSession).where(
            DBSession.id == session_id,
            DBSession.status == "active",
        )
    )
    db_session = session_result.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found or closed")

    # Step 1: æ¢å– token
    try:
        token_info = await spotify_service.exchange_token(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    access_token = token_info["access_token"]

    # Step 2: èŽ·å–ç”¨æˆ·ä¿¡æ¯
    try:
        user_info = await spotify_service.get_current_user(access_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get user info: {e}")

    # Step 3: åˆ›å»º Guest è®°å½•
    guest = Guest(
        session_id=session_id,
        spotify_user_id=user_info["spotify_user_id"],
        display_name=user_info["display_name"],
        access_token=token_info["access_token"],
        refresh_token=token_info["refresh_token"],
        token_expires_at=token_info["expires_at"],
    )
    db.add(guest)
    await db.flush()  # èŽ·å– guest.id

    # åŽç»­æ•°æ®èŽ·å–ï¼ˆå¦‚ top tracksï¼‰ç”± Guest åœ¨å‰ç«¯ä¸»åŠ¨è§¦å‘

    # é‡å®šå‘åˆ°å‰ç«¯æ­Œå•é€‰æ‹©é¡µé¢
    redirect_url = f"{settings.FRONTEND_URL}/guest/{guest.id}?session_id={session_id_str}"
    return RedirectResponse(url=redirect_url)


# â”€â”€ DJ OAuth Flow â”€â”€

def _get_dj_oauth_manager() -> SpotifyOAuth:
    """åˆ›å»º DJ ä¸“ç”¨ SpotifyOAuthï¼ˆéœ€è¦ playlist-modify æƒé™ï¼‰"""
    settings = get_settings()
    # DJ OAuth å›žè°ƒæŒ‡å‘åŽç«¯ /auth/dj/callback
    # ä»Ž FRONTEND_URL æŽ¨æ–­åŽç«¯åœ°å€ï¼ˆåŒä¸»æœº port 8000ï¼‰
    import re
    base = re.sub(r':\d+$', ':8000', settings.FRONTEND_URL)
    dj_redirect_uri = f"{base}/auth/dj/callback"
    return SpotifyOAuth(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        redirect_uri=dj_redirect_uri,
        scope="playlist-modify-public playlist-modify-private user-read-private",
        show_dialog=True,
        open_browser=False,
    )


@router.get("/dj/login")
async def dj_login(session_id: str = Query(..., description="DJ session ID")):
    """DJ è¿žæŽ¥ Spotify â€” ç”ŸæˆæŽˆæƒ URL"""
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    oauth = _get_dj_oauth_manager()
    # state å‰ç¼€ dj_ åŒºåˆ† DJ å’Œ Guest å›žè°ƒ
    authorize_url = oauth.get_authorize_url(state=f"dj_{session_id}")
    return RedirectResponse(url=authorize_url)


@router.get("/dj/callback")
async def dj_callback(
    code: str = Query(...),
    state: str = Query(""),
):
    """DJ Spotify OAuth å›žè°ƒ â€” æ¢å– token å¹¶ç¼“å­˜"""
    settings = get_settings()

    # ä»Ž state æ¢å¤ session_idï¼ˆæ ¼å¼ï¼šdj_{session_id}ï¼‰
    if not state.startswith("dj_"):
        raise HTTPException(status_code=400, detail="Invalid state for DJ callback")

    session_id_str = state[3:]  # åŽ»æŽ‰ "dj_" å‰ç¼€
    try:
        uuid.UUID(session_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id in state")

    # æ¢å– token
    oauth = _get_dj_oauth_manager()
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        token_info = await loop.run_in_executor(
            None, lambda: oauth.get_access_token(code, as_dict=True, check_cache=False)
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DJ token exchange failed: {e}")

    access_token = token_info["access_token"]

    # ç¼“å­˜åˆ° dj_playlist æ¨¡å—
    from app.routers.dj_playlist import _session_dj_tokens
    _session_dj_tokens[session_id_str] = access_token

    # é‡å®šå‘å›žå‰ç«¯ DJ å·¥ä½œå°
    redirect_url = f"{settings.FRONTEND_URL}/dj/{session_id_str}?dj_connected=true"
    return RedirectResponse(url=redirect_url)
