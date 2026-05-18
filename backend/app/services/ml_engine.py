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
import random
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
    for rank, item in enumerate(tracks[:20], start=1):
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
    previous_rec_ids: set,
    guest_count: int,
    db: AsyncSession,
) -> list[dict] | None:
    """
    Use Spotify Recommendations API with crowd audio feature targets.
    Returns None if the API call fails (triggers LLM fallback).
    """
    target_features = _compute_crowd_features(guest_tracks) if guest_tracks else {}

    # Build seed_tracks from random guest submissions for variety
    seed_track_ids = []
    if guest_tracks:
        pool = [t.spotify_track_id for t in guest_tracks
                if t.spotify_track_id and not t.spotify_track_id.startswith("llm_")]
        if pool:
            seed_track_ids = random.sample(pool, min(3, len(pool)))

    # Slightly perturb target features for variety on each refresh
    if target_features:
        perturbed = {}
        for k, v in target_features.items():
            if k == "tempo":
                perturbed[k] = v + random.uniform(-8, 8)  # ±8 BPM
            else:
                perturbed[k] = max(0.0, min(1.0, v + random.uniform(-0.08, 0.08)))
        target_features = perturbed

    # Determine genre seeds for this call — shuffle to get different combos
    genres_for_call = list(genre_seeds) if genre_seeds else ["pop"]
    random.shuffle(genres_for_call)
    # Spotify allows max 5 seeds total (genres + tracks combined)
    max_genres = 5 - len(seed_track_ids)
    genres_for_call = genres_for_call[:max_genres]

    print(f"[ml_engine] Spotify recs: genres={genres_for_call}, seed_tracks={seed_track_ids}, features={target_features}")

    tracks = await spotify_service.get_recommendations_by_seeds(
        access_token=dj_token,
        seed_genres=genres_for_call,
        seed_tracks=seed_track_ids or None,
        limit=100,  # Request more tracks for bigger pool
        target_features=target_features or None,
    )

    if not tracks:
        print("[ml_engine] Spotify recommendations returned empty, falling back to LLM")
        return None

    # Filter already-added tracks, previous recommendations, and deduplicate
    seen = set(already_added_ids)
    filtered_fresh = []  # tracks not in previous recommendations
    filtered_repeat = []  # tracks that were in previous recommendations (fallback)
    for t in tracks:
        tid = t["spotify_track_id"]
        if tid not in seen:
            seen.add(tid)
            if tid in previous_rec_ids:
                filtered_repeat.append(t)
            else:
                filtered_fresh.append(t)

    # Prefer fresh tracks, fill remaining from repeat pool if needed
    random.shuffle(filtered_fresh)
    random.shuffle(filtered_repeat)
    combined = filtered_fresh + filtered_repeat

    if not combined:
        return None

    selected = combined[:10]

    # Score by popularity for the selected tracks
    selected.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    top = [dict(t, score=1.0 - i * 0.04) for i, t in enumerate(selected)]

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
    previous_rec_text: str,
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

    # Generate a refresh seed so the LLM is forced to give different results each time
    refresh_seed = random.randint(1000, 9999)

    prompt = f"""You are an elite, modern DJ assistant.

REFRESH SEED: {refresh_seed} — This is a new refresh request. You MUST recommend a COMPLETELY DIFFERENT set of songs from any previous response. Do NOT repeat songs from earlier.

ABSOLUTE #1 RULE - GENRE LOCK: Every single song you recommend MUST be {genre_str}. This overrides every other rule. If any song is not clearly {genre_str}, do not include it.

DJ's party genre: {genre_str}

TRENDING ARTISTS CONTEXT (use as inspiration only):
{internet_context}

Guests' submitted tracks (reference only, genre lock still applies):
{guest_info_str}

ALREADY ADDED TO PLAYLIST (DO NOT RECOMMEND AGAIN):
{already_added_text}

PREVIOUSLY RECOMMENDED (DO NOT RECOMMEND AGAIN, pick completely new songs):
{previous_rec_text}

Recommend exactly 10 songs. All 10 must be {genre_str}.

For new_hits: 5 fresh {genre_str} tracks not in the guest list above and not previously recommended.
For guest_picks: up to 5 tracks from the guest list that are genuinely {genre_str}. If fewer than 5 qualify, fill the remaining slots in new_hits instead. NEVER include an off-genre song just to fill a guest_picks slot.

Other requirements:
- Real, verified songs only. No hallucinated titles or album names.
- Prefer post-2020 releases. No overplayed party cliches.
- Zero overlap between new_hits and guest_picks.
- Every song must have a real artist name you are certain about.
- Pick songs from a DIFFERENT set of artists than any previously recommended.

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
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.95,  # Higher temperature for more variety on refresh
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

async def recompute(session_id: uuid.UUID, db: AsyncSession, use_track_seeds: bool = False) -> list[dict]:
    print(f"[ml_engine] recompute called, session_id={session_id}")

    # 1. Tracks already added to DJ playlist (exclude from recommendations)
    playlist_result = await db.execute(text(
        "SELECT track_name, artist_name, spotify_track_id FROM playlist_tracks WHERE session_id = :sid"
    ), {"sid": session_id})
    playlist_rows = playlist_result.fetchall()
    already_added_ids = {r.spotify_track_id for r in playlist_rows if r.spotify_track_id}
    already_added_text = "\n".join(f"{r.track_name} - {r.artist_name}" for r in playlist_rows) or "None"

    # 2. Previously recommended tracks (to avoid repeating on refresh)
    prev_rec_result = await db.execute(text(
        "SELECT track_name, artist_name, spotify_track_id FROM recommendations WHERE session_id = :sid"
    ), {"sid": session_id})
    prev_rec_rows = prev_rec_result.fetchall()
    previous_rec_ids = {r.spotify_track_id for r in prev_rec_rows if r.spotify_track_id}
    previous_rec_text = "\n".join(f"{r.track_name} - {r.artist_name}" for r in prev_rec_rows) or "None"

    # 3. Session genre seeds
    session_result = await db.execute(select(DBSession).where(DBSession.id == session_id))
    db_session = session_result.scalar_one_or_none()
    if not db_session:
        return []
    genre_seeds = db_session.genre_seeds or []

    # 4. All guest tracks for this session (with audio features + display_name)
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

    # 5. Guest count (including guests who haven't submitted tracks yet)
    gc_result = await db.execute(text(
        "SELECT COUNT(DISTINCT id) FROM guests WHERE session_id = :sid"
    ), {"sid": session_id})
    guest_count = gc_result.scalar() or 0

    print(f"[ml_engine] guest_count={guest_count}, track_count={len(guest_tracks)}, prev_recs={len(previous_rec_ids)}")

    # 6. Try Spotify content-based filtering (requires DJ token)
    dj_token = None
    try:
        from app.routers.dj_playlist import _session_dj_tokens
        dj_token = _session_dj_tokens.get(str(session_id))
    except (ImportError, AttributeError):
        pass

    if dj_token:
        result = await _spotify_recompute(
            session_id, dj_token, genre_seeds, guest_tracks,
            already_added_ids, previous_rec_ids, guest_count, db
        )
        if result:
            print(f"[ml_engine] Spotify content-based (DJ token): {len(result)} recommendations")
            return result

    # 7. Spotify Search fallback (no user login needed, returns real verified tracks)
    print("[ml_engine] Trying Spotify search")

    search_genres = genre_seeds if genre_seeds else ["pop"]

    # Build full artist pool for these genres
    artist_pool: list[str] = []
    for g in search_genres:
        artist_pool.extend(spotify_service._GENRE_ARTISTS.get(g, []))

    if not artist_pool:
        artist_pool = spotify_service._GENRE_ARTISTS.get("pop", [])

    # Randomly sample 4 distinct artists so each call returns different tracks
    sample_size = min(4, len(artist_pool))
    selected_artists = random.sample(artist_pool, sample_size)
    print(f"[ml_engine] Selected artists for search: {selected_artists}")

    all_search_tracks: list[dict] = []
    seen_ids: set[str] = set()
    for artist in selected_artists:
        offset = random.choice([0, 10, 20, 30])
        batch = await spotify_service.search_tracks_by_artist(artist, limit=10, offset=offset)
        for t in batch:
            if t["spotify_track_id"] not in seen_ids:
                seen_ids.add(t["spotify_track_id"])
                all_search_tracks.append(t)
        if len(all_search_tracks) >= 30:
            break

    if all_search_tracks:
        seen = set(already_added_ids) | previous_rec_ids
        filtered = [t for t in all_search_tracks if t["spotify_track_id"] not in seen]
        # Shuffle instead of sorting by popularity so each refresh returns a different list
        random.shuffle(filtered)
        top = [dict(t, score=1.0 - i * 0.04) for i, t in enumerate(filtered[:20])]
        if top:
            is_cold = len(guest_tracks) == 0
            result = await _save_recommendations(session_id, top, db, guest_count, is_cold_start=is_cold)
            print(f"[ml_engine] Spotify search: {len(result)} recommendations")
            return result

    # 8. LLM fallback (last resort)
    print("[ml_engine] Using LLM fallback")
    return await _llm_recompute(
        session_id, genre_seeds, guest_tracks, already_added_text,
        previous_rec_text, guest_count, db
    )
