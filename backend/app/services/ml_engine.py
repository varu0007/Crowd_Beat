"""
ml_engine.py â€” æŽ¨èç®—æ³•å¼•æ“Ž
èŒè´£ï¼š
  - æ­£å¸¸æ¨¡å¼ï¼šä½¿ç”¨ Gemini API è¿›è¡ŒæŽ¨è
  - Cold startï¼šhost é¢„è®¾ genre fallback
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
import json
import re
from collections import defaultdict

import numpy as np
from sqlalchemy import select, delete, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from google import genai

from app.config import get_settings
from app.models.database import (
    Session as DBSession,
    Guest,
    GuestTrack,
    Recommendation,
)
from app.services import spotify_service


_TRACK_SCHEMA = {
    "type": "object",
    "properties": {
        "track_name": {"type": "string"},
        "artist_name": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["track_name", "artist_name", "reason"],
}

_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "new_hits": {
            "type": "array",
            "items": _TRACK_SCHEMA,
        },
        "guest_picks": {
            "type": "array",
            "items": _TRACK_SCHEMA,
        },
    },
    "required": ["new_hits", "guest_picks"],
}


def _generate_with_gemini(prompt: str) -> str:
    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config={
            "temperature": 0.35,
            "max_output_tokens": 2500,
            "response_mime_type": "application/json",
            "response_schema": _RECOMMENDATION_SCHEMA,
        },
    )
    return response.text or ""


def _parse_llm_recommendations(response_text: str) -> list[dict]:
    cleaned = response_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        parsed_json = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not match:
            match = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if not match:
            raise ValueError("Gemini returned invalid recommendation JSON")
        parsed_json = json.loads(match.group(0))

    recommendations_data = []
    if isinstance(parsed_json, dict):
        new_hits = parsed_json.get("new_hits", [])
        guest_picks = parsed_json.get("guest_picks", [])

        for item in new_hits[:5]:
            if isinstance(item, dict):
                item["source"] = "new"
                recommendations_data.append(item)

        for item in guest_picks[:5]:
            if isinstance(item, dict):
                item["source"] = "guest"
                recommendations_data.append(item)
    elif isinstance(parsed_json, list):
        for item in parsed_json[:10]:
            if isinstance(item, dict):
                item["source"] = item.get("source", "new").lower()
                recommendations_data.append(item)

    if not recommendations_data:
        raise ValueError("Gemini returned no usable recommendations")

    return recommendations_data


def _fetch_internet_context(genre_str: str) -> str:
    """ä½¿ç”¨ DuckDuckGo æœç´¢æœ€æ–°çš„æµè¡Œæ›²ç›®ï¼Œç»™å¤§æ¨¡åž‹è¡¥å……çŸ¥è¯†ç›²åŒºã€‚"""
    try:
        from ddgs import DDGS
        results = DDGS().text(
            f"trending {genre_str} artists 2024 2025 who are popular now",
            max_results=8
        )
        if results:
            # åªå–æ ‡é¢˜ï¼Œbody é‡Œçš„ä¿¡æ¯è´¨é‡å¤ªå·®å®¹æ˜“å¼•å…¥æ®‹ç¼ºæ•°æ®
            context = "\n".join([f"- {r['title']}" for r in results])
            print(f"[debug] internet context preview: {context[:300]}")
            return context[:1000]
    except Exception as e:
        print(f"[Internet Search Error] {e}")
    return "No internet context available."

async def recompute(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """
    ä½¿ç”¨ Gemini API é‡æ–°è®¡ç®—æŽ¨èåˆ—è¡¨ã€‚
    """
    print(f"[debug] recompute called, session_id={session_id}")
    settings = get_settings()

    # Fetch already added playlist tracks to exclude them from recommendations
    playlist_stmt = text("""
        SELECT track_name, artist_name
        FROM playlist_tracks
        WHERE session_id = :session_id
    """)
    playlist_result = await db.execute(playlist_stmt, {"session_id": session_id})
    playlist_rows = playlist_result.fetchall()
    already_added_strs = [f"{r.track_name} - {r.artist_name}" for r in playlist_rows]
    already_added_text = "\n".join(already_added_strs) if already_added_strs else "None"

    # 1. æŸ¥è¯¢è¯¥ session æ‰€æœ‰ guest_tracks
    stmt = text("""
        SELECT gt.track_name, gt.artist_name, gt.popularity, g.display_name
        FROM guest_tracks gt
        JOIN guests g ON gt.guest_id = g.id
        WHERE g.session_id = :session_id
    """)
    result = await db.execute(stmt, {"session_id": session_id})
    rows = result.fetchall()
    print(f"[debug] found {len(rows)} tracks")

    if not rows:
        session_result = await db.execute(
            select(DBSession).where(DBSession.id == session_id)
        )
        db_session = session_result.scalar_one_or_none()
        if not db_session:
            return []

        guest_count_result = await db.execute(
            select(func.count()).where(Guest.session_id == session_id)
        )
        guest_count = guest_count_result.scalar() or 0
        return await _cold_start_fallback(session_id, db_session, db, guest_count, [], already_added_text)

    # 3. ç»Ÿè®¡ guest æ•°é‡ï¼Œ< 2 äººèµ° cold_start_fallback
    guest_tracks_map = defaultdict(list)
    for row in rows:
        guest_tracks_map[row.display_name].append({
            "track": row.track_name,
            "artist": row.artist_name
        })

    # ç»Ÿè®¡çœŸå®ž guest æ•°é‡ï¼ˆåŒ…æ‹¬æ²¡æäº¤æ­Œæ›²çš„ guestï¼‰
    guest_count_result = await db.execute(text(
        "SELECT COUNT(DISTINCT id) as cnt FROM guests WHERE session_id = :session_id"
    ), {"session_id": session_id})
    guest_count = guest_count_result.scalar() or 0
    print(f"[debug] guest_count={guest_count}")
    print(f"[debug] real guest_count from DB = {guest_count}")
    if len(guest_tracks_map) == 0:
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
        return await _cold_start_fallback(session_id, db_session, db, guest_count, all_tracks, already_added_text)

    # 4. æŒ‰ guest åˆ†ç»„æ•´ç†æ­Œæ›²ï¼Œæ¯äººæœ€å¤šå– 10 é¦–
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

TRENDING ARTISTS CONTEXT (use these artist names as inspiration for who to recommend):
{internet_context}

Use this to identify which artists are currently popular in {genre_str}.
Then recommend real songs by these artists that you know with certainty exist.

Guests' musical tastes (for reference only, NEVER use this to break the DJ's genre rules):
{guest_info_str}

ALREADY ADDED TO PLAYLIST (CRITICAL: DO NOT RECOMMEND THESE SONGS AGAIN):
{already_added_text}

Please recommend exactly 10 songs suitable for the current party.
CRITICAL Recommendation Requirements:
- NO HALLUCINATIONS / REAL SINGLES ONLY: You MUST recommend verified, real, individual song tracks. Do NOT recommend compilation albums, generic genre labels, or playlist titles.
- DO NOT INVENT SONGS: If the internet context does not contain enough clear, unambiguous song names, IGNORE THE CONTEXT and use your own pre-trained knowledge. NEVER invent song titles or use placeholders like "New Artist".
- DO NOT SPLIT ALBUM NAMES: Do NOT hallucinate fake song titles by splitting an album name or using a record label name as an artist (e.g., "Snatch! Records" is not an artist).
- TIME FRAME: Prefer songs released after 2020. Avoid songs older than 2015 unless they are absolute classics that still work in a party setting. Do NOT hallucinate release years â€” if you are unsure when a song was released, just omit the year.
- GENRE: The songs MUST strictly align with the DJ's set genres: {genre_str}.
- AVOID OUTDATED SONGS: Absolutely NO clichÃ©, overplayed, or outdated "generic party" anthems (e.g., do not recommend "Sandstorm" or "Macarena").
- SONG MIX RATIO (5:5): You MUST provide exactly 10 songs total. Exactly 5 songs MUST be brand new hits (NOT from the guests' list). Exactly 5 songs MUST be selected directly from the guests' submitted tracks provided above (choose the ones that best fit the genre).
- CRITICAL: The 5 songs in 'new_hits' MUST NOT be any song that appears in the guests' submitted tracks list above. new_hits are DJ-curated fresh discoveries ONLY. Cross-check every song in new_hits against the guest list before returning.
- IMPORTANT: There must be ZERO overlap between new_hits and guest_picks. Every song must appear exactly once across both lists combined.
- Ensure the vibe is suitable for a live party atmosphere within the specific requested genres.

VALIDATION RULES (apply before returning):
1. Album names are NOT songs. If you are unsure whether something is an album or a single, skip it and pick another song.
2. Every song must have a real, specific artist name. If you cannot identify the artist with certainty, skip that song.
3. Before returning, mentally verify each song exists as a real single on Spotify. If uncertain, replace it with a song you are 100% sure about.

Return exactly one JSON object matching the configured schema.
Use only the keys new_hits, guest_picks, track_name, artist_name, and reason."""

    # 6. è°ƒç”¨ Gemini
    print(f"[debug] prompt preview (last 500 chars): {prompt[-500:]}")
    try:
        response_text = _generate_with_gemini(prompt)
        print(f"[debug] raw LLM response: {response_text[:500]}")
    except Exception as e:
        print(f"[Gemini API Error] {e}")
        raise RuntimeError(f"Gemini request failed: {e}") from e

    # 7. JSON è§£æž
    recommendations_data = _parse_llm_recommendations(response_text)

    # 8. DELETE æ—§ recommendations, INSERT Top-20
    await db.execute(
        delete(Recommendation).where(Recommendation.session_id == session_id)
    )

    now = datetime.now(timezone.utc)
    results = []
    import hashlib
    for i, item in enumerate(recommendations_data):
        rank = i + 1
        score = 1.0 - (rank - 1) * 0.04
        track_name = item.get("track_name", "Unknown Track")
        artist_name = item.get("artist_name", "Unknown Artist")
        source = item.get("source", "new")
        safe_name = f"{track_name}-{artist_name}".lower().encode('utf-8')
        spotify_track_id = f"llm_{source}_{hashlib.md5(safe_name).hexdigest()[:10]}"

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

    # 9. await db.commit()ï¼Œè¿”å›žåˆ—è¡¨
    await db.commit()
    return results


async def _cold_start_fallback(
    session_id: uuid.UUID,
    db_session: "DBSession",
    db: AsyncSession,
    guest_count: int,
    existing_tracks: list[GuestTrack] = None,
    already_added_text: str = "None",
) -> list[dict]:
    """
    Cold start å¤„ç† (Gemini API ç‰ˆæœ¬)ï¼š
    - ä½¿ç”¨ host é¢„è®¾çš„ genre_seeds
    - å¦‚æžœæœ‰å°‘é‡ guest tracksï¼Œæå–ä¸€äº›æ­Œæ›²åç§°ä½œä¸ºä¸Šä¸‹æ–‡
    - è°ƒç”¨ Gemini API ç”ŸæˆæŽ¨è
    """
    settings = get_settings()
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

TRENDING ARTISTS CONTEXT (use these artist names as inspiration for who to recommend):
{internet_context}

Use this to identify which artists are currently popular in {genre_str}.
Then recommend real songs by these artists that you know with certainty exist.

{"Here is the musical taste of existing guests: " + crowd_summary if crowd_summary else ""}

ALREADY ADDED TO PLAYLIST (CRITICAL: DO NOT RECOMMEND THESE SONGS AGAIN):
{already_added_text}

Please strictly recommend 10 songs in the {genre_str} style.
CRITICAL Requirements:
- NO HALLUCINATIONS / REAL SINGLES ONLY: You MUST recommend verified, real, individual song tracks. Do NOT recommend compilation albums, generic genre labels, or playlist titles.
- DO NOT INVENT SONGS: If the internet context lacks enough real songs, rely on your internal knowledge. NEVER invent songs or use "New Artist".
- DO NOT SPLIT ALBUM NAMES: Do NOT hallucinate fake song titles by splitting an album name or confusing record labels with artists.
- TIME FRAME: Prefer songs released after 2020. Avoid songs older than 2015 unless they are absolute classics that still work in a party setting. Do NOT hallucinate release years â€” if you are unsure when a song was released, just omit the year.
- GENRE: MUST be strictly of the {genre_str} style.
- AVOID OUTDATED SONGS: Absolutely NO clichÃ©, overplayed, or outdated "generic party" anthems.
- SONG MIX RATIO (5:5): You MUST provide exactly 10 songs total. Exactly 5 songs MUST be brand new hits. Exactly 5 songs MUST be selected directly from the existing guests' tracks provided above (if any exist and fit the genre).
- CRITICAL: The 5 songs in 'new_hits' MUST NOT be any song that appears in the guests' submitted tracks list above. new_hits are DJ-curated fresh discoveries ONLY. Cross-check every song in new_hits against the guest list before returning.
- CRITICAL for new_hits: These MUST be songs that are NOT in the guest's submitted tracks. These are fresh DJ discoveries from the internet search context. Do NOT pick songs from the guest's list for new_hits under any circumstances. Cross-check: if a song appears in the guest taste section, it cannot appear in new_hits.
- IMPORTANT: There must be ZERO overlap between new_hits and guest_picks. Every song must appear exactly once across both lists combined.
- Ensure the vibe is suitable for a live party atmosphere within the requested genre constraints.

VALIDATION RULES (apply before returning):
1. Album names are NOT songs. If you are unsure whether something is an album or a single, skip it and pick another song.
2. Every song must have a real, specific artist name. If you cannot identify the artist with certainty, skip that song.
3. Before returning, mentally verify each song exists as a real single on Spotify. If uncertain, replace it with a song you are 100% sure about.

Return exactly one JSON object matching the configured schema.
Use only the keys new_hits, guest_picks, track_name, artist_name, and reason."""

    try:
        response_text = _generate_with_gemini(prompt)
    except Exception as e:
        print(f"[Gemini API Error] Cold Start: {e}")
        raise RuntimeError(f"Gemini request failed: {e}") from e

    recommendations_data = _parse_llm_recommendations(response_text)

    top_n = []
    import hashlib
    for i, rec in enumerate(recommendations_data[:10]):
        source = rec.get("source", "new")
        t_name = rec.get("track_name", "Unknown Track")
        a_name = rec.get("artist_name", "Unknown Artist")
        safe_name = f"{t_name}-{a_name}".lower().encode('utf-8')
        top_n.append({
            "spotify_track_id": f"llm_cold_{source}_{hashlib.md5(safe_name).hexdigest()[:10]}",
            "track_name": t_name,
            "artist_name": a_name,
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
    """å°†æŽ¨èç»“æžœå†™å…¥æ•°æ®åº“ï¼ˆå…ˆåˆ æ—§æ•°æ®å†æ’å…¥ï¼‰"""
    # åˆ é™¤è¯¥ session çš„æ—§æŽ¨è
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
