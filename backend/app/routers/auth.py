"""
auth.py — Spotify OAuth 路由
端点：
  GET  /auth/login       → 生成 Spotify 授权 URL
  GET  /auth/callback    → 接收回调，换取 token，获取 top tracks + audio features
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
    Guest 扫码后跳转到此端点
    生成 Spotify 授权 URL，将 session_id 编码在 state 参数中
    """
    # 验证 session_id 格式
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
    Spotify OAuth 回调

    流程：
    1. 用 code 换取 access_token
    2. 获取用户信息
    3. 获取 top tracks
    4. 获取 audio features
    5. 存入数据库
    6. 触发推荐重算 + WebSocket 广播
    7. 重定向到前端成功页
    """
    settings = get_settings()

    # 从 state 恢复 session_id
    session_id_str = state
    try:
        session_id = uuid.UUID(session_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state (session_id)")

    # 验证 session 存在且活跃
    session_result = await db.execute(
        select(DBSession).where(
            DBSession.id == session_id,
            DBSession.status == "active",
        )
    )
    db_session = session_result.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found or closed")

    # Step 1: 换取 token
    try:
        token_info = await spotify_service.exchange_token(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    access_token = token_info["access_token"]

    # Step 2: 获取用户信息
    try:
        user_info = await spotify_service.get_current_user(access_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get user info: {e}")

    # Step 3: 创建 Guest 记录
    guest = Guest(
        session_id=session_id,
        spotify_user_id=user_info["spotify_user_id"],
        display_name=user_info["display_name"],
        access_token=token_info["access_token"],
        refresh_token=token_info["refresh_token"],
        token_expires_at=token_info["expires_at"],
    )
    db.add(guest)
    await db.flush()  # 获取 guest.id

    # 后续数据获取（如 top tracks）由 Guest 在前端主动触发

    # 重定向到前端歌单选择页面
    redirect_url = f"{settings.FRONTEND_URL}/guest/{guest.id}?session_id={session_id_str}"
    return RedirectResponse(url=redirect_url)


# ── DJ OAuth Flow ──

def _get_dj_oauth_manager() -> SpotifyOAuth:
    """创建 DJ 专用 SpotifyOAuth（需要 playlist-modify 权限）"""
    settings = get_settings()
    # DJ OAuth 回调指向后端 /auth/dj/callback
    # 从 FRONTEND_URL 推断后端地址（同主机 port 8000）
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
    """DJ 连接 Spotify — 生成授权 URL"""
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    oauth = _get_dj_oauth_manager()
    # state 前缀 dj_ 区分 DJ 和 Guest 回调
    authorize_url = oauth.get_authorize_url(state=f"dj_{session_id}")
    return RedirectResponse(url=authorize_url)


@router.get("/dj/callback")
async def dj_callback(
    code: str = Query(...),
    state: str = Query(""),
):
    """DJ Spotify OAuth 回调 — 换取 token 并缓存"""
    settings = get_settings()

    # 从 state 恢复 session_id（格式：dj_{session_id}）
    if not state.startswith("dj_"):
        raise HTTPException(status_code=400, detail="Invalid state for DJ callback")

    session_id_str = state[3:]  # 去掉 "dj_" 前缀
    try:
        uuid.UUID(session_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id in state")

    # 换取 token
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

    # 缓存到 dj_playlist 模块
    from app.routers.dj_playlist import _session_dj_tokens
    _session_dj_tokens[session_id_str] = access_token

    # 重定向回前端 DJ 工作台
    redirect_url = f"{settings.FRONTEND_URL}/dj/{session_id_str}?dj_connected=true"
    return RedirectResponse(url=redirect_url)
