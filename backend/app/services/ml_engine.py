"""
ml_engine.py — 推荐算法引擎
职责：
  - 正常模式：使用 Gemini API 进行推荐
  - Cold start：host 预设 genre fallback
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
import json
import re
from collections import defaultdict

import numpy as np
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from google import genai
from duckduckgo_search import DDGS

from app.config import get_settings
from app.models.database import (
    Session as DBSession,
    Guest,
    GuestTrack,
    Recommendation,
)
from app.services import spotify_service


def _generate_with_gemini(prompt: str) -> str:
    """Generate recommendation JSON with Gemini."""
    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config={
            "temperature": 0.7,
            "max_output_tokens": 2000,
            "response_mime_type": "application/json",
        },
    )
    return response.text or ""


def _fetch_internet_context(genre_str: str) -> str:
    """使用 DuckDuckGo 搜索最新的流行曲目，给大模型补充知识盲区。"""
    try:
        results = DDGS().text(f"top {genre_str} hit singles tracks 2024 2025 2026", max_results=10)
        if results:
            context = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
            return context
    except Exception as e:
        print(f"[Internet Search Error] {e}")
    return "No internet context available."

async def recompute(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """
    使用 Gemini API 重新计算推荐列表。
    """
    print(f"[debug] recompute called, session_id={session_id}")

    # 1. 查询该 session 所有 guest_tracks
    stmt = text("""
        SELECT gt.track_name, gt.artist_name, gt.popularity, g.display_name
        FROM guest_tracks gt
        JOIN guests g ON gt.guest_id = g.id
        WHERE g.session_id = :session_id
    """)
    result = await db.execute(stmt, {"session_id": session_id})
    rows = result.fetchall()
    print(f"[debug] found {len(rows)} tracks")

    # 2. 没数据返回 []
    if not rows:
        session_result = await db.execute(
            select(DBSession).where(DBSession.id == session_id)
        )
        db_session = session_result.scalar_one_or_none()
        if not db_session:
            return []

        return await _cold_start_fallback(session_id, db_session, db, 0, [])

    # 3. 统计 guest 数量，< 2 人走 cold_start_fallback
    guest_tracks_map = defaultdict(list)
    for row in rows:
        guest_tracks_map[row.display_name].append({
            "track": row.track_name,
            "artist": row.artist_name
        })

    guest_count = len(guest_tracks_map)
    print(f"[debug] guest_count={guest_count}")
    if guest_count < 2:
        session_result = await db.execute(
            select(DBSession).where(DBSession.id == session_id)
        )
        db_session = session_result.scalar_one_or_none()
        if not db_session:
            return []
            
        tracks_result = await db.execute(
            select(GuestTrack).join(Guest, GuestTrack.guest_id == Guest.id).where(Guest.session_id == session_id)
        )
        all_tracks = tracks_result.scalars().all()
        return await _cold_start_fallback(session_id, db_session, db, guest_count, all_tracks)

    # 4. 按 guest 分组整理歌曲，每人最多取 10 首
    guest_lines = []
    for guest_name, tracks in guest_tracks_map.items():
        limited_tracks = tracks[:10]
        track_strs = [f"{t['track']} - {t['artist']}" for t in limited_tracks]
        guest_lines.append(f"Guest '{guest_name}' likes: " + ", ".join(track_strs))

    guest_info_str = "\n".join(guest_lines)

    genre_result = await db.execute(text(
        "SELECT genre_seeds FROM sessions WHERE id = :session_id"
    ), {"session_id": session_id})
    session_row = genre_result.mappings().first()
    genre_seeds = session_row["genre_seeds"] if session_row and session_row["genre_seeds"] else []
    genre_str = ", ".join(genre_seeds) if genre_seeds else "any suitable party genre"

    print(f"[debug] fetching internet context for {genre_str}...")
    import asyncio
    internet_context = await asyncio.to_thread(_fetch_internet_context, genre_str)

    prompt = f"""You are an elite, modern DJ assistant.

DJ's strictly set party genre(s): {genre_str}

LATEST INTERNET SEARCH CONTEXT (Use this to find brand new songs!):
{internet_context}

Guests' musical tastes (for reference only, NEVER use this to break the DJ's genre rules):
{guest_info_str}

Please recommend exactly 20 songs suitable for the current party.
CRITICAL Recommendation Requirements:
- NO HALLUCINATIONS / REAL SINGLES ONLY: You MUST recommend verified, real, individual song tracks. Do NOT recommend compilation albums, generic genre labels, or playlist titles.
- DO NOT INVENT SONGS: If the internet context does not contain enough clear, unambiguous song names, IGNORE THE CONTEXT and use your own pre-trained knowledge. NEVER invent song titles or use placeholders like "New Artist".
- DO NOT SPLIT ALBUM NAMES: Do NOT hallucinate fake song titles by splitting an album name or using a record label name as an artist (e.g., "Snatch! Records" is not an artist).
- TIME FRAME: MUST be extremely recent, released within the last 2-3 years maximum (2024-2026). Do NOT recommend songs older than 2023.
- GENRE: The songs MUST strictly align with the DJ's set genres: {genre_str}.
- AVOID OUTDATED SONGS: Absolutely NO cliché, overplayed, or outdated "generic party" anthems (e.g., do not recommend "Sandstorm" or "Macarena").
- Ensure the vibe is suitable for a live party atmosphere within the specific requested genres.
- Do not repeat songs already submitted by the guests.

Return strictly in JSON format, do not include any other text:
[{{ "track_name": "Song Name", "artist_name": "Artist Name", "reason": "Brief reason including release year" }}]"""

    # 6. 调用 Gemini
    try:
        response_text = _generate_with_gemini(prompt)
    except Exception as e:
        print(f"[Gemini API Error] {e}")
        raise RuntimeError(f"Gemini request failed: {e}") from e

    # 7. JSON 解析
    try:
        recommendations_data = json.loads(response_text)
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            try:
                recommendations_data = json.loads(match.group(0))
            except json.JSONDecodeError:
                print("[JSON Parse Error] fallback match failed.")
                raise ValueError("Gemini returned invalid recommendation JSON")
        else:
            print("[JSON Parse Error] Could not find JSON array.")
            raise ValueError("Gemini returned invalid recommendation JSON")

    if not isinstance(recommendations_data, list):
        raise ValueError("Gemini returned recommendation JSON that was not a list")

    # 取 top 20
    recommendations_data = recommendations_data[:20]

    # 8. DELETE 旧 recommendations, INSERT Top-20
    await db.execute(
        delete(Recommendation).where(Recommendation.session_id == session_id)
    )

    now = datetime.now(timezone.utc)
    results = []
    for i, item in enumerate(recommendations_data):
        rank = i + 1
        score = 1.0 - (rank - 1) * 0.04
        track_name = item.get("track_name", "Unknown Track")
        artist_name = item.get("artist_name", "Unknown Artist")
        spotify_track_id = f"llm_{rank}"

        rec = Recommendation(
            session_id=session_id,
            spotify_track_id=spotify_track_id,
            track_name=track_name,
            artist_name=artist_name,
            score=score,
            rank=rank,
            generated_at=now,
            guest_count=guest_count,
            is_cold_start=False,
        )
        db.add(rec)
        results.append({
            "spotify_track_id": spotify_track_id,
            "track_name": track_name,
            "artist_name": artist_name,
            "score": score,
            "rank": rank,
            "is_cold_start": False,
        })

    # 9. await db.commit()，返回列表
    await db.commit()
    return results


async def _cold_start_fallback(
    session_id: uuid.UUID,
    db_session: "DBSession",
    db: AsyncSession,
    guest_count: int,
    existing_tracks: list[GuestTrack] = None,
) -> list[dict]:
    """
    Cold start 处理 (Gemini API 版本)：
    - 使用 host 预设的 genre_seeds
    - 如果有少量 guest tracks，提取一些歌曲名称作为上下文
    - 调用 Gemini API 生成推荐
    """
    genre_seeds = db_session.genre_seeds or []
    genre_str = ", ".join(genre_seeds) if genre_seeds else "any suitable party genre"
    crowd_summary = ""
    if existing_tracks:
        track_names = [f"{t.track_name} - {t.artist_name}" for t in existing_tracks[:10]]
        crowd_summary = ", ".join(track_names)

    print(f"[debug] fetching internet context for {genre_str}...")
    import asyncio
    internet_context = await asyncio.to_thread(_fetch_internet_context, genre_str)

    prompt = f"""You are an elite, modern DJ assistant, specializing strictly in {genre_str} music.

Current party genre setting: {genre_str}

LATEST INTERNET SEARCH CONTEXT (Use this to find brand new songs!):
{internet_context}

{"Here is the musical taste of existing guests: " + crowd_summary if crowd_summary else ""}

Please strictly recommend 20 songs in the {genre_str} style.
CRITICAL Requirements:
- NO HALLUCINATIONS / REAL SINGLES ONLY: You MUST recommend verified, real, individual song tracks. Do NOT recommend compilation albums, generic genre labels, or playlist titles.
- DO NOT INVENT SONGS: If the internet context lacks 20 real songs, rely on your internal knowledge. NEVER invent songs or use "New Artist".
- DO NOT SPLIT ALBUM NAMES: Do NOT hallucinate fake song titles by splitting an album name or confusing record labels with artists.
- TIME FRAME: MUST be extremely recent, released within the last 2-3 years maximum (2024-2026). Do NOT recommend older songs.
- GENRE: MUST be strictly of the {genre_str} style.
- AVOID OUTDATED SONGS: Absolutely NO cliché, overplayed, or outdated "generic party" anthems.
- Ensure the vibe is suitable for a live party atmosphere within the requested genre constraints.

Return strictly in JSON format, do not include any other text:
[{{ "track_name": "Song Name", "artist_name": "Artist Name", "reason": "Brief reason including release year" }}]"""

    try:
        response_text = _generate_with_gemini(prompt)
    except Exception as e:
        print(f"[Gemini API Error] Cold Start: {e}")
        raise RuntimeError(f"Gemini request failed: {e}") from e

    try:
        recommendations_data = json.loads(response_text)
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            try:
                recommendations_data = json.loads(match.group(0))
            except json.JSONDecodeError:
                raise ValueError("Gemini returned invalid recommendation JSON")
        else:
            raise ValueError("Gemini returned invalid recommendation JSON")

    if not isinstance(recommendations_data, list):
        raise ValueError("Gemini returned recommendation JSON that was not a list")

    top_n = []
    for i, rec in enumerate(recommendations_data[:20]):
        top_n.append({
            "spotify_track_id": f"llm_cold_{i+1}",
            "track_name": rec.get("track_name", "Unknown Track"),
            "artist_name": rec.get("artist_name", "Unknown Artist"),
            "score": 1.0 - (i * 0.01),
        })

    recommendations = await _save_recommendations(
        session_id, top_n, db, guest_count, is_cold_start=True
    )
    return recommendations


async def _save_recommendations(
    session_id: uuid.UUID,
    top_n: list[dict],
    db: AsyncSession,
    guest_count: int,
    is_cold_start: bool,
) -> list[dict]:
    """将推荐结果写入数据库（先删旧数据再插入）"""
    # 删除该 session 的旧推荐
    await db.execute(
        delete(Recommendation).where(Recommendation.session_id == session_id)
    )

    now = datetime.now(timezone.utc)
    results = []
    for rank, item in enumerate(top_n, start=1):
        rec = Recommendation(
            session_id=session_id,
            spotify_track_id=item["spotify_track_id"],
            track_name=item["track_name"],
            artist_name=item["artist_name"],
            score=item["score"],
            rank=rank,
            generated_at=now,
            guest_count=guest_count,
            is_cold_start=is_cold_start,
        )
        db.add(rec)
        results.append({
            "spotify_track_id": item["spotify_track_id"],
            "track_name": item["track_name"],
            "artist_name": item["artist_name"],
            "score": item["score"],
            "rank": rank,
            "is_cold_start": is_cold_start,
        })

    await db.commit()
    return results
