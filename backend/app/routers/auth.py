"""CrowdBeat module."""

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
    """Internal helper."""
    # ---
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    authorize_url = spotify_service.get_authorize_url(session_id=session_id)
    return RedirectResponse(url=authorize_url)


@router.get("/login_with_profile")
async def login_with_profile(
    session_id: str = Query(..., description="DJ session ID to join"),
    username: str = Query(..., description="Guest username"),
    email: str = Query(..., description="Guest email"),
    db: AsyncSession = Depends(get_db),
):
    """Start Spotify OAuth but preserve username/email in the OAuth state."""
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    # state must round-trip through Spotify callback.
    # Keep it compact; backend will decode using json.
    import json
    from urllib.parse import quote

    state_payload = {
        "v": 1,
        "session_id": session_id,
        "username": username,
        "email": email,
    }
    state = quote(json.dumps(state_payload, separators=(",", ":")))

    from app.models.database import GuestInfo
    try:
        guest_info = GuestInfo(
            session_id=uuid.UUID(session_id),
            username=username,
            email=email
        )
        db.add(guest_info)
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"Failed to save guest info: {e}")

    authorize_url = spotify_service.get_authorize_url(session_id=session_id, oauth_state=state)
    return RedirectResponse(url=authorize_url)



@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Internal helper."""
    settings = get_settings()

    # ---
    session_id_str = state

    # New profile-carrying state: urlencoded JSON.
    # Legacy state: raw session_id uuid.
    import json
    from urllib.parse import unquote

    decoded = None
    try:
        decoded_candidate = unquote(state)
        decoded = json.loads(decoded_candidate)
    except Exception:
        decoded = None

    if decoded and decoded.get('v') == 1:
        session_id_str = decoded.get('session_id')
    
    try:
        session_id = uuid.UUID(session_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state (session_id)")


    # ---
    session_result = await db.execute(
        select(DBSession).where(
            DBSession.id == session_id,
            DBSession.status == "active",
        )
    )
    db_session = session_result.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found or closed")

    # ---
    try:
        token_info = await spotify_service.exchange_token(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    access_token = token_info["access_token"]

    # ---
    try:
        user_info = await spotify_service.get_current_user(access_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get user info: {e}")

    # ---
    # Spotify "email" may be unavailable unless the user grants the correct scope.
    # Avoid hard failure by making it optional.
    guest = Guest(
        session_id=session_id,
        spotify_user_id=user_info["spotify_user_id"],
        display_name=user_info["display_name"],
        email=user_info.get("email") or "",
        access_token=token_info["access_token"],
        refresh_token=token_info["refresh_token"],
        token_expires_at=token_info["expires_at"],
    )


    db.add(guest)
    await db.flush()  # ---

    # ---

    # ---
    redirect_url = f"{settings.FRONTEND_URL}/guest/{guest.id}?session_id={session_id_str}"
    return RedirectResponse(url=redirect_url)


# ---

def _get_dj_oauth_manager() -> SpotifyOAuth:
    """Internal helper."""
    settings = get_settings()
    # ---
    # ---
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
    """Internal helper."""
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    oauth = _get_dj_oauth_manager()
    # ---
    authorize_url = oauth.get_authorize_url(state=f"dj_{session_id}")
    return RedirectResponse(url=authorize_url)


@router.get("/dj/callback")
async def dj_callback(
    code: str = Query(...),
    state: str = Query(""),
):
    """Internal helper."""
    settings = get_settings()

    # ---
    if not state.startswith("dj_"):
        raise HTTPException(status_code=400, detail="Invalid state for DJ callback")

    session_id_str = state[3:]  # ---
    try:
        uuid.UUID(session_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id in state")

    # ---
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

    # ---
    from app.routers.dj_playlist import _session_dj_tokens
    _session_dj_tokens[session_id_str] = access_token

    # ---
    redirect_url = f"{settings.FRONTEND_URL}/dj/{session_id_str}?dj_connected=true"
    return RedirectResponse(url=redirect_url)
