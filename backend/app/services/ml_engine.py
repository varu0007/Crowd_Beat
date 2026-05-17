"""
ml_engine.py - Recommendation engine

Primary path: Content-based filtering via Spotify Recommendations API
  1. Compute average audio feature vector from all guest tracks (crowd profile)
  2. Call Spotify /recommendations with seed_genres + target features
  3. Returns real, existing Spotify tracks

Fallback (LLM): Used when DJ is not connected to Spotify or Spotify API fails
"""

import uuid
import json
import os
import re
import hashlib
import asyncio
from datetime import datetime, timezone
from collections import defaultdict

import numpy as np
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from groq import Groq
from duckduckgo_search import DDGS

from app.config import get_settings
from app.models.database import Session as DBSession, Guest, GuestTrack, Recommendation
from app.services import spotify_service


# ---------------------------------------------------------------------------
# Crowd feature computation
# ---------------------------------------------------------------------------

def _compute_crowd_features(guest_tracks: list) -> dict:
    """
    Average audio features across all guest tracks to build a crowd profile.
    Only includes features where data exists (audio features may be null if
    Spotify API returned no data for some tracks).
    """
    feature_keys = ["danceability", "energy", "valence", "acousticness", "instrumentalness"]
    result = {}
    for key in feature_keys:
        values = [getattr(t, key) for t in guest_tracks if getattr(t, key) is not None]
        if values:
            result[key] = sum(values) / len(values)
    tempos = [t.tempo for t in guest_tracks if t.tempo is not None]
    if tempos:
        result["tempo"] = sum(tempos) / len(tempos)
    return result


# ---------------------------------------------------------------------------
# Internet search for LLM context
# ---------------------------------------------------------------------------

def _fetch_internet_context(genre_str: str) -> str:
    try:
        results = DDGS().text(
            f"trending {genre_str} artists 2024 2025 who are popular now",
            max_results=8
        )
        if results:
            context = "\n".join([f"- {r['title']}" for r in results])
            return context[:1000]
    except Exception as e:
        print(f"[ml_engine] internet search error: {e}")
    return "No internet context available."


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

async def _save_recommendations(
    session_id: uuid.UUID,
    tracks: list[dict],
    db: AsyncSession,
    guest_count: int,
    is_cold_start: bool,
) -> list[dict]:
    await db.execute(delete(Recommendation).where(Recommendation.session_id == session_id))
    now = datetime.now(timezone.utc)
    results = []
    for rank, item in enumerate(tracks[:10], start=1):
        rec = Recommendation(
            session_id=session_id,
            spotify_track_id=item["spotify_track_id"],
            track_name=item["track_name"],
            artist_name=item["artist_name"],
            score=item.get("score", 1.0 - (rank - 1) * 0.04),
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
            "score": rec.score,
            "rank": rank,
            "is_cold_start": is_cold_start,
        })
    await db.commit()
    return results


# ---------------------------------------------------------------------------
# Primary: Spotify content-based filtering
# ---------------------------------------------------------------------------

async def _spotify_recompute(
    session_id: uuid.UUID,
    dj_token: str,
    genre_seeds: list[str],
    guest_tracks: list,
    already_added_ids: set,
    guest_count: int,
    db: AsyncSession,
) -> list[dict] | None:
    """
    Use Spotify Recommendations API with crowd audio feature targets.
    Returns None if the API call fails (triggers LLM fallback).
    """
    target_features = _compute_crowd_features(guest_tracks) if guest_tracks else {}

    print(f"[ml_engine] Spotify recs: genres={genre_seeds}, features={target_features}")

    tracks = await spotify_service.get_recommendations_by_seeds(
        access_token=dj_token,
        seed_genres=genre_seeds[:5] if genre_seeds else ["pop"],
        limit=30,
        target_features=target_features or None,
    )

    if not tracks:
        print("[ml_engine] Spotify recommendations returned empty, falling back to LLM")
        return None

    # Filter already-added tracks and deduplicate
    seen = set(already_added_ids)
    filtered = []
    for t in tracks:
        if t["spotify_track_id"] not in seen:
            seen.add(t["spotify_track_id"])
            filtered.append(t)

    if not filtered:
        return None

    # Score by popularity, take top 10
    filtered.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    top = [dict(t, score=1.0 - i * 0.04) for i, t in enumerate(filtered[:10])]

    is_cold = len(guest_tracks) == 0
    return await _save_recommendations(session_id, top, db, guest_count, is_cold_start=is_cold)


# ---------------------------------------------------------------------------
# Fallback: LLM-based recommendations
# ---------------------------------------------------------------------------

async def _llm_recompute(
    session_id: uuid.UUID,
    genre_seeds: list[str],
    guest_tracks: list,
    already_added_text: str,
    guest_count: int,
    db: AsyncSession,
) -> list[dict]:
    genre_str = ", ".join(genre_seeds) if genre_seeds else "any suitable party genre"

    # Build guest info string
    guest_tracks_map = defaultdict(list)
    for t in guest_tracks:
        guest_tracks_map[t.display_name].append({"track": t.track_name, "artist": t.artist_name})

    if guest_tracks_map:
        guest_lines = []
        for name, tracks in guest_tracks_map.items():
            strs = [f"{t['track']} - {t['artist']}" for t in tracks[:10]]
            guest_lines.append(f"Guest '{name}' likes: " + ", ".join(strs))
        guest_info_str = "\n".join(guest_lines)
    else:
        guest_info_str = "No guest data yet."

    internet_context = await asyncio.to_thread(_fetch_internet_context, genre_str)

    prompt = f"""You are an elite, modern DJ assistant.

ABSOLUTE #1 RULE - GENRE LOCK: Every single song you recommend MUST be {genre_str}. This overrides every other rule. If any song is not clearly {genre_str}, do not include it.

DJ's party genre: {genre_str}

TRENDING ARTISTS CONTEXT (use as inspiration only):
{internet_context}

Guests' submitted tracks (reference only, genre lock still applies):
{guest_info_str}

ALREADY ADDED TO PLAYLIST (DO NOT RECOMMEND AGAIN):
{already_added_text}

Recommend exactly 10 songs. All 10 must be {genre_str}.

For new_hits: 5 fresh {genre_str} tracks not in the guest list above.
For guest_picks: up to 5 tracks from the guest list that are genuinely {genre_str}. If fewer than 5 qualify, fill the remaining slots in new_hits instead. NEVER include an off-genre song just to fill a guest_picks slot.

Other requirements:
- Real, verified songs only. No hallucinated titles or album names.
- Prefer post-2020 releases. No overplayed party cliches.
- Zero overlap between new_hits and guest_picks.
- Every song must have a real artist name you are certain about.

Return strictly in this JSON format with no other text:
{{
  "new_hits": [
    {{ "track_name": "Song Name", "artist_name": "Artist Name", "reason": "Brief reason" }}
  ],
  "guest_picks": [
    {{ "track_name": "Song Name", "artist_name": "Artist Name", "reason": "Brief reason" }}
  ]
}}"""

    try:
        from dotenv import load_dotenv
        load_dotenv()
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7,
        )
        response_text = response.choices[0].message.content
    except Exception as e:
        print(f"[ml_engine] Groq API error: {e}")
        return []

    # Parse JSON
    parsed = None
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return []

    if not parsed:
        return []

    items = []
    if isinstance(parsed, dict):
        for item in parsed.get("new_hits", [])[:5]:
            item["source"] = "new"
            items.append(item)
        for item in parsed.get("guest_picks", [])[:5]:
            item["source"] = "guest"
            items.append(item)
    elif isinstance(parsed, list):
        items = parsed[:10]

    tracks = []
    for i, item in enumerate(items):
        t_name = item.get("track_name", "Unknown Track")
        a_name = item.get("artist_name", "Unknown Artist")
        source = item.get("source", "new")
        safe = f"{t_name}-{a_name}".lower().encode("utf-8")
        tracks.append({
            "spotify_track_id": f"llm_{source}_{hashlib.md5(safe).hexdigest()[:10]}",
            "track_name": t_name,
            "artist_name": a_name,
            "score": 1.0 - i * 0.04,
        })

    is_cold = len(guest_tracks) == 0
    return await _save_recommendations(session_id, tracks, db, guest_count, is_cold_start=is_cold)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def recompute(session_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    print(f"[ml_engine] recompute called, session_id={session_id}")

    # 1. Tracks already added to DJ playlist (exclude from recommendations)
    playlist_result = await db.execute(text(
        "SELECT track_name, artist_name, spotify_track_id FROM playlist_tracks WHERE session_id = :sid"
    ), {"sid": session_id})
    playlist_rows = playlist_result.fetchall()

    previous_result = await db.execute(text(
        "SELECT track_name, artist_name, spotify_track_id FROM recommendations WHERE session_id = :sid"
    ), {"sid": session_id})
    previous_rows = previous_result.fetchall()

    already_added_ids = {
        r.spotify_track_id
        for r in [*playlist_rows, *previous_rows]
        if r.spotify_track_id
    }
    excluded_lines = [
        f"{r.track_name} - {r.artist_name}"
        for r in [*playlist_rows, *previous_rows]
        if r.track_name and r.artist_name
    ]
    already_added_text = "\n".join(excluded_lines) or "None"

    # 2. Session genre seeds
    session_result = await db.execute(select(DBSession).where(DBSession.id == session_id))
    db_session = session_result.scalar_one_or_none()
    if not db_session:
        return []
    genre_seeds = db_session.genre_seeds or []

    # 3. All guest tracks for this session (with audio features + display_name)
    rows = await db.execute(text("""
        SELECT gt.spotify_track_id, gt.track_name, gt.artist_name,
               gt.danceability, gt.energy, gt.valence, gt.tempo,
               gt.acousticness, gt.instrumentalness, gt.popularity,
               g.display_name
        FROM guest_tracks gt
        JOIN guests g ON gt.guest_id = g.id
        WHERE g.session_id = :sid
    """), {"sid": session_id})

    class _Track:
        pass

    guest_tracks = []
    for r in rows.fetchall():
        t = _Track()
        for col in ("spotify_track_id", "track_name", "artist_name", "danceability",
                    "energy", "valence", "tempo", "acousticness", "instrumentalness",
                    "popularity", "display_name"):
            setattr(t, col, getattr(r, col))
        guest_tracks.append(t)

    # 4. Guest count (including guests who haven't submitted tracks yet)
    gc_result = await db.execute(text(
        "SELECT COUNT(DISTINCT id) FROM guests WHERE session_id = :sid"
    ), {"sid": session_id})
    guest_count = gc_result.scalar() or 0

    print(f"[ml_engine] guest_count={guest_count}, track_count={len(guest_tracks)}")

    # 5. Try Spotify content-based filtering (requires DJ token)
    from app.routers.dj_playlist import _session_dj_tokens
    dj_token = _session_dj_tokens.get(str(session_id))

    if dj_token:
        result = await _spotify_recompute(
            session_id, dj_token, genre_seeds, guest_tracks,
            already_added_ids, guest_count, db
        )
        if result:
            print(f"[ml_engine] Spotify content-based: {len(result)} recommendations")
            return result

    # 6. LLM fallback
    print("[ml_engine] Using LLM fallback")
    return await _llm_recompute(
        session_id, genre_seeds, guest_tracks, already_added_text, guest_count, db
    )
