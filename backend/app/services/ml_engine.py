"""Recommendation engine backed by Gemini."""

import uuid
from datetime import datetime, timezone
from typing import Optional
import json
import re
import hashlib
import importlib
from collections import defaultdict

import numpy as np
from sqlalchemy import select, delete, text, func
from sqlalchemy.ext.asyncio import AsyncSession

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

    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("google-genai is not installed") from exc

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
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return json.dumps(parsed)
    return response.text or ""


def _normalize_track(item: dict) -> dict | None:
    track_name = (
        item.get("track_name")
        or item.get("track")
        or item.get("title")
        or item.get("name")
        or item.get("song")
    )
    artist_name = (
        item.get("artist_name")
        or item.get("artist")
        or item.get("artists")
        or item.get("artistName")
    )

    if isinstance(artist_name, list):
        artist_name = ", ".join(str(artist) for artist in artist_name)

    if not track_name or not artist_name:
        return None

    return {
        "track_name": str(track_name).strip(),
        "artist_name": str(artist_name).strip(),
        "reason": str(item.get("reason", "")),
        "source": str(item.get("source", "new")).lower(),
    }


def _extract_recommendation_items(parsed_json) -> list[dict]:
    if isinstance(parsed_json, list):
        return [item for item in parsed_json if isinstance(item, dict)]

    if not isinstance(parsed_json, dict):
        return []

    items: list[dict] = []
    for source, key in (("new", "new_hits"), ("guest", "guest_picks")):
        for item in parsed_json.get(key, []) or []:
            if isinstance(item, dict):
                item["source"] = source
                items.append(item)

    if items:
        return items

    for key in ("recommendations", "tracks", "songs", "items", "results"):
        value = parsed_json.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


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
    for item in _extract_recommendation_items(parsed_json)[:10]:
        normalized = _normalize_track(item)
        if normalized:
            recommendations_data.append(normalized)

    if not recommendations_data:
        raise ValueError("Gemini returned no usable recommendations")

    return recommendations_data


def _fetch_internet_context(genre_str: str) -> str:
    """Fetch a compact current-music context for the requested genre."""
    try:
        DDGS = importlib.import_module("ddgs").DDGS
        results = DDGS().text(
            f"trending {genre_str} artists 2024 2025 who are popular now",
            max_results=8,
        )
        if results:
            context = "\n".join([f"- {r['title']}" for r in results])
            print(f"[debug] internet context preview: {context[:300]}")
            return context[:1000]
    except Exception as e:
        print(f"[Internet Search Error] {e}")
    return "No internet context available."


def _rank_guest_tracks(rows) -> list[dict]:
    """Rank guest tracks using weighted audio features from config.

    Each track gets a composite score from the configurable weights:
      danceability, energy, valence, tempo (normalised), acousticness,
      instrumentalness.  Popularity is used as a tiebreaker at 10 % weight.
    Duplicate (name, artist) pairs are merged by taking the best score seen.
    """
    settings = get_settings()

    # Normalise tempo: typical party BPM range 60–200.
    _TEMPO_MIN, _TEMPO_MAX = 60.0, 200.0

    def _audio_score(row) -> float:
        def _get(attr: str) -> float | None:
            val = getattr(row, attr, None)
            try:
                return float(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        dance = _get("danceability")
        energy = _get("energy")
        valence = _get("valence")
        raw_tempo = _get("tempo")
        acoustic = _get("acousticness")
        instrumental = _get("instrumentalness")
        popularity_raw = _get("popularity")

        has_audio_features = any(v is not None for v in (dance, energy, valence, raw_tempo))

        if has_audio_features:
            # Full audio-feature score
            dance = dance if dance is not None else 0.5
            energy = energy if energy is not None else 0.5
            valence = valence if valence is not None else 0.5
            tempo_norm = max(0.0, min(1.0, ((raw_tempo or 120.0) - _TEMPO_MIN) / (_TEMPO_MAX - _TEMPO_MIN)))
            acoustic = acoustic if acoustic is not None else 0.3
            instrumental = instrumental if instrumental is not None else 0.1
            popularity = (popularity_raw or 50.0) / 100.0

            score = (
                settings.WEIGHT_DANCEABILITY        * dance
                + settings.WEIGHT_ENERGY            * energy
                + settings.WEIGHT_VALENCE           * valence
                + settings.WEIGHT_TEMPO             * tempo_norm
                + settings.WEIGHT_ACOUSTICNESS      * (1.0 - acoustic)
                + settings.WEIGHT_INSTRUMENTALNESS  * (1.0 - instrumental)
                + 0.10                              * popularity
            )
        else:
            # Audio Features API is unavailable (deprecated) — rank purely by popularity
            # so tracks at least sort differently rather than all getting the same score.
            popularity = (popularity_raw or 0.0) / 100.0
            score = 0.4 + 0.5 * popularity  # range 0.40–0.90, avoids false tie at 0.53

        return round(min(1.0, max(0.0, score)), 4)

    # Deduplicate by (track_name, artist_name), keep best score
    best: dict[tuple[str, str], dict] = {}
    for row in rows:
        track_name = (row.track_name or "Unknown Track").strip()
        artist_name = (row.artist_name or "Unknown Artist").strip()
        key = (track_name.lower(), artist_name.lower())
        score = _audio_score(row)
        if key not in best or score > best[key]["score"]:
            digest = hashlib.md5(f"{track_name}-{artist_name}".lower().encode("utf-8")).hexdigest()[:10]
            best[key] = {
                "spotify_track_id": f"guest_{digest}",
                "track_name": track_name,
                "artist_name": artist_name,
                "score": score,
            }

    ranked = sorted(best.values(), key=lambda item: item["score"], reverse=True)
    return ranked[:10]


def _genre_seed_recommendations(genre_seeds: list[str]) -> list[dict]:
    genre_text = " ".join(genre_seeds).lower()
    if "electronic" in genre_text or "edm" in genre_text or "dance" in genre_text:
        picks = [
            ("Rumble", "Skrillex, Fred again.. & Flowdan"),
            ("Where You Are", "John Summit & Hayla"),
            ("Atmosphere", "FISHER & Kita Alexander"),
            ("Miracle", "Calvin Harris & Ellie Goulding"),
            ("Disconnect", "Becky Hill & Chase & Status"),
            ("Baddadan", "Chase & Status"),
            ("Saving Up", "Dom Dolla"),
            ("Prada", "casso, RAYE & D-Block Europe"),
            ("Both", "Tiesto & BIA"),
            ("Ray Of Solar", "Swedish House Mafia"),
        ]
    elif "hip" in genre_text or "rap" in genre_text:
        picks = [
            ("Not Like Us", "Kendrick Lamar"),
            ("Paint The Town Red", "Doja Cat"),
            ("SkeeYee", "Sexyy Red"),
            ("First Person Shooter", "Drake feat. J. Cole"),
            ("Lovin On Me", "Jack Harlow"),
            ("FE!N", "Travis Scott feat. Playboi Carti"),
            ("Barbie World", "Nicki Minaj & Ice Spice"),
            ("Surround Sound", "JID feat. 21 Savage & Baby Tate"),
            ("Players", "Coi Leray"),
            ("Tomorrow 2", "GloRilla & Cardi B"),
        ]
    elif "pop" in genre_text:
        picks = [
            ("Espresso", "Sabrina Carpenter"),
            ("Houdini", "Dua Lipa"),
            ("Training Season", "Dua Lipa"),
            ("greedy", "Tate McRae"),
            ("Paint The Town Red", "Doja Cat"),
            ("Water", "Tyla"),
            ("yes, and?", "Ariana Grande"),
            ("Cruel Summer", "Taylor Swift"),
            ("Flowers", "Miley Cyrus"),
            ("Dance The Night", "Dua Lipa"),
        ]
    else:
        picks = [
            ("Rumble", "Skrillex, Fred again.. & Flowdan"),
            ("Espresso", "Sabrina Carpenter"),
            ("Houdini", "Dua Lipa"),
            ("Water", "Tyla"),
            ("Prada", "casso, RAYE & D-Block Europe"),
            ("Where You Are", "John Summit & Hayla"),
            ("Paint The Town Red", "Doja Cat"),
            ("greedy", "Tate McRae"),
            ("Miracle", "Calvin Harris & Ellie Goulding"),
            ("Disconnect", "Becky Hill & Chase & Status"),
        ]

    results = []
    for index, (track_name, artist_name) in enumerate(picks):
        digest = hashlib.md5(f"{track_name}-{artist_name}".lower().encode("utf-8")).hexdigest()[:10]
        results.append({
            "spotify_track_id": f"seed_{digest}",
            "track_name": track_name,
            "artist_name": artist_name,
            "score": max(0.1, 1.0 - index * 0.04),
        })
    return results


async def _save_ranked_tracks(
    session_id: uuid.UUID,
    top_n: list[dict],
    db: AsyncSession,
    guest_count: int,
    is_cold_start: bool,
) -> list[dict]:
    if not top_n:
        return []

    return await _save_recommendations(
        session_id=session_id,
        top_n=top_n,
        db=db,
        guest_count=guest_count,
        is_cold_start=is_cold_start,
    )


async def recompute(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """Recompute a session's recommendations with Gemini."""
    print(f"[debug] recompute called, session_id={session_id}")

    playlist_stmt = text("""
        SELECT track_name, artist_name
        FROM playlist_tracks
        WHERE session_id = :session_id
    """)
    playlist_result = await db.execute(playlist_stmt, {"session_id": session_id})
    playlist_rows = playlist_result.fetchall()
    already_added_strs = [f"{r.track_name} - {r.artist_name}" for r in playlist_rows]
    already_added_text = "\n".join(already_added_strs) if already_added_strs else "None"

    playlist_keys = {
        (row.track_name.strip().lower(), row.artist_name.strip().lower())
        for row in playlist_rows
        if row.track_name and row.artist_name
    }

    # Fetch audio features alongside track info so scoring and prompts can use them
    stmt = text("""
        SELECT
            gt.track_name, gt.artist_name, gt.popularity,
            gt.danceability, gt.energy, gt.valence,
            gt.tempo, gt.acousticness, gt.instrumentalness,
            g.display_name
        FROM guest_tracks gt
        JOIN guests g ON gt.guest_id = g.id
        WHERE g.session_id = :session_id
    """)
    result = await db.execute(stmt, {"session_id": session_id})
    rows = result.fetchall()
    print(f"[debug] found {len(rows)} tracks")

    # Count guests up front so cold-start threshold can be applied consistently
    guest_count_result = await db.execute(text(
        "SELECT COUNT(DISTINCT id) as cnt FROM guests WHERE session_id = :session_id"
    ), {"session_id": session_id})
    guest_count = guest_count_result.scalar() or 0
    print(f"[debug] guest_count={guest_count}")

    settings = get_settings()

    # No tracks at all -> pure cold start
    if not rows:
        session_result = await db.execute(
            select(DBSession).where(DBSession.id == session_id)
        )
        db_session = session_result.scalar_one_or_none()
        if not db_session:
            return []
        return await _cold_start_fallback(session_id, db_session, db, guest_count, [], already_added_text, playlist_keys)

    # Below guest threshold -> cold start (may still use existing tracks as hints)
    if guest_count < settings.COLD_START_THRESHOLD:
        print(f"[debug] below cold-start threshold ({guest_count} < {settings.COLD_START_THRESHOLD}), using cold-start path")
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
        return await _cold_start_fallback(session_id, db_session, db, guest_count, all_tracks, already_added_text, playlist_keys)

    # ------------------------------------------------------------------ #
    # Warm-start: build per-guest track lists + aggregate audio features  #
    # ------------------------------------------------------------------ #
    guest_tracks_map: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        guest_tracks_map[row.display_name].append({
            "track": row.track_name,
            "artist": row.artist_name,
        })

    def _safe_float(val, default=None):
        try:
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    # Aggregate audio features across all guest tracks for the Gemini prompt
    feature_sums = {f: 0.0 for f in ("danceability", "energy", "valence", "tempo", "acousticness", "instrumentalness")}
    feature_counts = {f: 0 for f in feature_sums}
    for row in rows:
        for feat in feature_sums:
            v = _safe_float(getattr(row, feat, None))
            if v is not None:
                feature_sums[feat] += v
                feature_counts[feat] += 1

    audio_summary_parts = []
    for feat in feature_sums:
        cnt = feature_counts[feat]
        if cnt > 0:
            avg = feature_sums[feat] / cnt
            audio_summary_parts.append(f"{feat.capitalize()}: {avg:.2f}")
    audio_summary = ", ".join(audio_summary_parts) if audio_summary_parts else "No audio data available"
    print(f"[debug] crowd audio profile: {audio_summary}")

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

    async def save_guest_track_fallback() -> list[dict]:
        """Fallback: use genre-seeded curated tracks when Gemini is unavailable.
        
        We intentionally do NOT return the guests' own submitted tracks here —
        that would show users songs they already know and own.
        """
        print("[recommendations] using genre-seed fallback (Gemini unavailable)")
        seeded = _genre_seed_recommendations(genre_seeds)
        return await _save_ranked_tracks(
            session_id=session_id,
            top_n=seeded,
            db=db,
            guest_count=guest_count,
            is_cold_start=True,
        )

    print(f"[debug] fetching internet context for {genre_str}...")
    import asyncio
    internet_context = await asyncio.to_thread(_fetch_internet_context, genre_str)

    prompt = f"""You are an elite, modern DJ assistant.

DJ's strictly set party genre(s): {genre_str}

TRENDING ARTISTS CONTEXT (use these artist names as inspiration for who to recommend):
{internet_context}

Use this to identify which artists are currently popular in {genre_str}.
Then recommend real songs by these artists that you know with certainty exist.

CROWD AUDIO PROFILE (average Spotify audio features across all guest tracks — use this to match the vibe):
{audio_summary}
Interpret these values: Danceability/Energy/Valence are 0–1 (higher = more danceable/energetic/positive).
Tempo is in BPM. Acousticness/Instrumentalness are 0–1 (higher = more acoustic/instrumental).
Prioritise recommending songs that match this crowd's vibe closely.

Guests' musical tastes (for reference only, NEVER use this to break the DJ's genre rules):
{guest_info_str}

ALREADY ADDED TO PLAYLIST (CRITICAL: DO NOT RECOMMEND THESE SONGS AGAIN):
{already_added_text}

Please recommend exactly 10 songs suitable for the current party.
CRITICAL Recommendation Requirements:
- NO HALLUCINATIONS / REAL SINGLES ONLY: You MUST recommend verified, real, individual song tracks. Do NOT recommend compilation albums, generic genre labels, or playlist titles.
- DO NOT INVENT SONGS: If the internet context does not contain enough clear, unambiguous song names, IGNORE THE CONTEXT and use your own pre-trained knowledge. NEVER invent song titles or use placeholders like "New Artist".
- DO NOT SPLIT ALBUM NAMES: Do NOT hallucinate fake song titles by splitting an album name or using a record label name as an artist.
- TIME FRAME: Prefer songs released after 2020. Avoid songs older than 2015 unless they are absolute classics that still work in a party setting. Do NOT hallucinate release years. If you are unsure when a song was released, omit the year.
- GENRE: The songs MUST strictly align with the DJ's set genres: {genre_str}.
- AVOID OUTDATED SONGS: Absolutely NO cliche, overplayed, or outdated generic party anthems.
- SONG MIX RATIO (5:5): You MUST provide exactly 10 songs total. Exactly 5 songs MUST be brand new hits (NOT from the guests' list). Exactly 5 songs in 'guest_picks' MUST be NEW songs inspired by the guests' musical taste — songs the guests would love but that DO NOT appear anywhere in their submitted tracks list above.
- CRITICAL: NEITHER new_hits NOR guest_picks may contain any song that appears in the guests' submitted tracks list above. All 10 recommendations must be fresh discoveries the guests haven't already submitted.
- IMPORTANT: There must be ZERO overlap between new_hits and guest_picks. Every song must appear exactly once across both lists combined.
- Ensure the vibe is suitable for a live party atmosphere within the specific requested genres.

VALIDATION RULES (apply before returning):
1. Album names are NOT songs. If you are unsure whether something is an album or a single, skip it and pick another song.
2. Every song must have a real, specific artist name. If you cannot identify the artist with certainty, skip that song.
3. Before returning, mentally verify each song exists as a real single on Spotify. If uncertain, replace it with a song you are 100% sure about.

Return exactly one JSON object matching the configured schema.
Use only the keys new_hits, guest_picks, track_name, artist_name, and reason."""

    print(f"[debug] prompt preview (last 500 chars): {prompt[-500:]}")
    try:
        response_text = _generate_with_gemini(prompt)
        print(f"[debug] raw LLM response: {response_text[:500]}")
        recommendations_data = _parse_llm_recommendations(response_text)
    except Exception as e:
        print(f"[Gemini Recommendation Error] {e}")
        return await save_guest_track_fallback()

    if not recommendations_data:
        return await save_guest_track_fallback()

    # Build a set of guest-submitted (track, artist) pairs for deduplication.
    # Even if Gemini ignores the prompt instructions, we enforce the rule in code.
    submitted_keys = {
        (row.track_name.strip().lower(), row.artist_name.strip().lower())
        for row in rows
        if row.track_name and row.artist_name
    }
    submitted_keys.update(playlist_keys)

    filtered_recommendations = []
    for item in recommendations_data:
        t = (item.get("track_name", "").strip().lower(), item.get("artist_name", "").strip().lower())
        if t in submitted_keys:
            print(f"[recommendations] filtered out guest-submitted track from results: {item.get('track_name')} - {item.get('artist_name')}")
            continue
        filtered_recommendations.append(item)

    if not filtered_recommendations:
        print("[recommendations] all LLM results were guest-submitted tracks, falling back")
        return await save_guest_track_fallback()

    recommendations_data = filtered_recommendations

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

    await db.commit()

    if not results:
        return await save_guest_track_fallback()

    return results


async def _cold_start_fallback(
    session_id: uuid.UUID,
    db_session: "DBSession",
    db: AsyncSession,
    guest_count: int,
    existing_tracks: list[GuestTrack] = None,
    already_added_text: str = "None",
    playlist_keys: set = None,
) -> list[dict]:
    """Generate cold-start recommendations when guest data is sparse."""
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
- TIME FRAME: Prefer songs released after 2020. Avoid songs older than 2015 unless they are absolute classics that still work in a party setting. Do NOT hallucinate release years. If you are unsure when a song was released, omit the year.
- GENRE: MUST be strictly of the {genre_str} style.
- AVOID OUTDATED SONGS: Absolutely NO cliche, overplayed, or outdated generic party anthems.
- SONG MIX RATIO (5:5): You MUST provide exactly 10 songs total. Exactly 5 songs MUST be brand new hits. Exactly 5 songs in 'guest_picks' MUST be NEW songs inspired by the existing guests' musical taste — songs they would love but that DO NOT appear anywhere in their submitted tracks listed above.
- CRITICAL: NEITHER new_hits NOR guest_picks may contain any song that appears in the guests' submitted tracks list above. All 10 recommendations must be fresh discoveries.
- CRITICAL for new_hits: These MUST be songs that are NOT in the guest's submitted tracks. These are fresh DJ discoveries from the internet search context. Do NOT pick songs from the guest's list for new_hits under any circumstances.
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
        recommendations_data = _parse_llm_recommendations(response_text)
    except Exception as e:
        print(f"[Gemini Recommendation Error] Cold Start: {e}")
        # Always fall back to curated genre seeds — never return the guest's own submitted tracks
        seeded = _genre_seed_recommendations(genre_seeds)
        return await _save_ranked_tracks(session_id, seeded, db, guest_count, is_cold_start=True)

    # Build exclusion set from existing_tracks so Gemini's guest_picks
    # can never echo back the user's own submitted songs.
    submitted_keys_cold = set()
    if existing_tracks:
        for t in existing_tracks:
            if t.track_name and t.artist_name:
                submitted_keys_cold.add((t.track_name.strip().lower(), t.artist_name.strip().lower()))

    if playlist_keys:
        submitted_keys_cold.update(playlist_keys)

    filtered_data = []
    for rec in recommendations_data:
        key = (rec.get("track_name", "").strip().lower(), rec.get("artist_name", "").strip().lower())
        if key in submitted_keys_cold:
            print(f"[cold_start] filtered out guest-submitted track: {rec.get('track_name')} - {rec.get('artist_name')}")
            continue
        filtered_data.append(rec)

    if not filtered_data:
        print("[cold_start] all LLM results matched guest tracks, using genre seeds")
        seeded = _genre_seed_recommendations(genre_seeds)
        return await _save_ranked_tracks(session_id, seeded, db, guest_count, is_cold_start=True)

    top_n = []
    for i, rec in enumerate(filtered_data[:10]):
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
    """Replace stored recommendations for a session."""
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