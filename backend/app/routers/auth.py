"""CrowdBeat module."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from app.config import get_settings
from app.models.database import get_db, Guest, GuestInfo, GuestTrack, Session as DBSession
from app.services import spotify_service, crowd_engine
from spotipy.oauth2 import SpotifyOAuth

router = APIRouter(prefix="/auth", tags=["auth"])


class ApprovalRequest(BaseModel):
    session_id: str = Field(..., description="DJ session ID to join")
    username: str = Field(..., min_length=2, max_length=200)
    email: str = Field(..., min_length=3, max_length=200)


async def _get_active_session(session_id: str, db: AsyncSession) -> tuple[uuid.UUID, DBSession]:
    try:
        sid = uuid.UUID(session_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    session_result = await db.execute(
        select(DBSession).where(DBSession.id == sid, DBSession.status == "active")
    )
    db_session = session_result.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found or closed")
    return sid, db_session


@router.post("/approval-request")
async def create_approval_request(
    req: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create or refresh a pending guest approval request before Spotify OAuth."""
    session_id, _ = await _get_active_session(req.session_id, db)
    email = req.email.strip().lower()
    username = req.username.strip()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")

    result = await db.execute(
        select(Guest).where(Guest.session_id == session_id, Guest.email == email)
    )
    guest = result.scalars().first()
    if guest:
        guest.spotify_username = username
        guest.display_name = guest.display_name or username
    else:
        guest = Guest(
            session_id=session_id,
            spotify_username=username,
            display_name=username,
            email=email,
            approval_status="pending",
        )
        db.add(guest)
        await db.flush()

    guest_info = GuestInfo(session_id=session_id, username=username, email=email)
    db.add(guest_info)
    await db.commit()

    return {
        "guest_id": str(guest.id),
        "session_id": str(session_id),
        "approval_status": guest.approval_status,
        "spotify_username": guest.spotify_username,
        "email": guest.email,
    }


@router.get("/approval-status/{guest_id}")
async def get_approval_status(
    guest_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return the current manual Spotify developer approval status for a guest."""
    try:
        gid = uuid.UUID(guest_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid guest_id")

    result = await db.execute(select(Guest).where(Guest.id == gid))
    guest = result.scalar_one_or_none()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    return {
        "guest_id": str(guest.id),
        "session_id": str(guest.session_id),
        "approval_status": guest.approval_status,
        "spotify_username": guest.spotify_username,
        "email": guest.email,
    }


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
    guest_id: str | None = Query(None, description="Pending guest approval request ID"),
    db: AsyncSession = Depends(get_db),
):
    """Start Spotify OAuth but preserve username/email in the OAuth state."""
    sid, _ = await _get_active_session(session_id, db)

    approved_guest = None
    if guest_id:
        try:
            gid = uuid.UUID(guest_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid guest_id")

        result = await db.execute(
            select(Guest).where(Guest.id == gid, Guest.session_id == sid)
        )
        approved_guest = result.scalar_one_or_none()
        if not approved_guest:
            raise HTTPException(status_code=404, detail="Guest approval request not found")
        if approved_guest.approval_status not in {"approved", "connected"}:
            raise HTTPException(status_code=403, detail="Guest is still pending approval")

    # state must round-trip through Spotify callback.
    # Keep it compact; backend will decode using json.
    import json
    from urllib.parse import quote

    state_payload = {
        "v": 1,
        "session_id": session_id,
        "username": username,
        "email": email,
        "guest_id": str(approved_guest.id) if approved_guest else None,
    }
    state = quote(json.dumps(state_payload, separators=(",", ":")))

    if not approved_guest:
        try:
            guest_info = GuestInfo(session_id=sid, username=username, email=email)
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


    await _get_active_session(session_id_str, db)

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

    guest = None
    if decoded and decoded.get("guest_id"):
        try:
            guest_id = uuid.UUID(decoded["guest_id"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid guest_id in state")

        result = await db.execute(
            select(Guest).where(Guest.id == guest_id, Guest.session_id == session_id)
        )
        guest = result.scalar_one_or_none()
        if not guest:
            raise HTTPException(status_code=404, detail="Guest approval request not found")
        if guest.approval_status not in {"approved", "connected"}:
            raise HTTPException(status_code=403, detail="Guest is still pending approval")

        guest.spotify_user_id = user_info["spotify_user_id"]
        guest.spotify_username = guest.spotify_username or decoded.get("username") or user_info["display_name"]
        guest.display_name = user_info["display_name"]
        guest.email = guest.email or decoded.get("email") or user_info.get("email") or ""
        guest.access_token = token_info["access_token"]
        guest.refresh_token = token_info["refresh_token"]
        guest.token_expires_at = token_info["expires_at"]
        guest.approval_status = "connected"
    else:
        # Legacy OAuth path: create a guest immediately after Spotify returns.
        guest = Guest(
            session_id=session_id,
            spotify_user_id=user_info["spotify_user_id"],
            spotify_username=(decoded or {}).get("username") or user_info["display_name"],
            display_name=user_info["display_name"],
            email=(decoded or {}).get("email") or user_info.get("email") or "",
            approval_status="connected",
            access_token=token_info["access_token"],
            refresh_token=token_info["refresh_token"],
            token_expires_at=token_info["expires_at"],
        )
        db.add(guest)

    await db.flush()  # ---
    await db.commit()

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
