"""Recommendation generation for CrowdBeat.

The engine uses Gemini first. If Gemini is unavailable or returns unusable
tracks, it falls back to curated genre seed lists. Existing playlist tracks and
the current recommendation board are excluded so pressing Refresh can produce a
meaningfully different set.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import random
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import (
    Guest,
    GuestTrack,
    Recommendation,
    Session as DBSession,
)


RecommendationKey = tuple[str, str]

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
        "new_hits": {"type": "array", "items": _TRACK_SCHEMA},
        "guest_picks": {"type": "array", "items": _TRACK_SCHEMA},
    },
    "required": ["new_hits", "guest_picks"],
}


_GENRE_SEEDS: dict[str, list[tuple[str, str]]] = {
    "electronic": [
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
        ("Breathe", "The Prodigy"),
        ("One More Time", "Daft Punk"),
        ("Strobe", "deadmau5"),
        ("Animals", "Martin Garrix"),
        ("Titanium", "David Guetta & Sia"),
        ("Levels", "Avicii"),
        ("Wake Me Up", "Avicii"),
        ("Don't You Worry Child", "Swedish House Mafia"),
        ("Clarity", "Zedd"),
        ("Summer", "Calvin Harris"),
        ("Turn On The Lights again..", "Fred again.. & Swedish House Mafia"),
        ("Baby again..", "Fred again.., Skrillex & Four Tet"),
        ("Fine Day Anthem", "Skrillex & Boys Noize"),
        ("Jungle", "Fred again.."),
        ("Delilah (pull me out of this)", "Fred again.."),
        ("Marea (we've lost dancing)", "Fred again.. & The Blessed Madonna"),
        ("Eat Your Man", "Dom Dolla & Nelly Furtado"),
        ("Take It Off", "FISHER & Aatig"),
        ("Losing It", "FISHER"),
        ("Drugs From Amsterdam", "Mau P"),
        ("Metro", "Kevin de Vries & Mau P"),
        ("Move", "Adam Port, Stryv & Malachiii"),
        ("Mwaki", "Zerb & Sofiya Nzau"),
        ("Pedro", "Jaxomy, Agatino Romero & Raffaella Carra"),
        ("Tell Me Why", "Supermode"),
        ("Innerbloom", "RUFUS DU SOL"),
        ("On My Knees", "RUFUS DU SOL"),
        ("Alive", "Anyma"),
        ("Consciousness", "Anyma & Chris Avantgarde"),
        ("The Sign", "Anyma & CamelPhat"),
    ],
    "hiphop": [
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
        ("Sicko Mode", "Travis Scott"),
        ("Humble", "Kendrick Lamar"),
        ("God's Plan", "Drake"),
        ("In Da Club", "50 Cent"),
        ("Lose Yourself", "Eminem"),
        ("Gold Digger", "Kanye West"),
        ("Niggas In Paris", "JAY-Z & Kanye West"),
        ("Bodak Yellow", "Cardi B"),
        ("Rockstar", "Post Malone"),
        ("Hotline Bling", "Drake"),
        ("Like That", "Future, Metro Boomin & Kendrick Lamar"),
        ("Type Shit", "Future, Metro Boomin, Travis Scott & Playboi Carti"),
        ("Carnival", "Kanye West, Ty Dolla $ign & Rich The Kid"),
        ("Jimmy Cooks", "Drake feat. 21 Savage"),
        ("Knife Talk", "Drake feat. 21 Savage & Project Pat"),
        ("Industry Baby", "Lil Nas X & Jack Harlow"),
        ("Superhero", "Metro Boomin, Future & Chris Brown"),
        ("Too Many Nights", "Metro Boomin, Don Toliver & Future"),
        ("MELTDOWN", "Travis Scott feat. Drake"),
        ("Sprinter", "Dave & Central Cee"),
        ("Doja", "Central Cee"),
        ("Just Wanna Rock", "Lil Uzi Vert"),
        ("N95", "Kendrick Lamar"),
        ("Family Ties", "Baby Keem & Kendrick Lamar"),
        ("Rich Flex", "Drake & 21 Savage"),
        ("Creepin'", "Metro Boomin, The Weeknd & 21 Savage"),
        ("I KNOW ?", "Travis Scott"),
        ("MY EYES", "Travis Scott"),
        ("All My Life", "Lil Durk feat. J. Cole"),
    ],
    "pop": [
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
        ("Bad Guy", "Billie Eilish"),
        ("Shape of You", "Ed Sheeran"),
        ("Uptown Funk", "Mark Ronson & Bruno Mars"),
        ("Blinding Lights", "The Weeknd"),
        ("As It Was", "Harry Styles"),
        ("Levitating", "Dua Lipa"),
        ("Watermelon Sugar", "Harry Styles"),
        ("Shake It Off", "Taylor Swift"),
        ("Anti-Hero", "Taylor Swift"),
        ("Good 4 U", "Olivia Rodrigo"),
        ("Please Please Please", "Sabrina Carpenter"),
        ("Taste", "Sabrina Carpenter"),
        ("Illusion", "Dua Lipa"),
        ("Rush", "Troye Sivan"),
        ("One Of Your Girls", "Troye Sivan"),
        ("vampire", "Olivia Rodrigo"),
        ("get him back!", "Olivia Rodrigo"),
        ("Strangers", "Kenya Grace"),
        ("Made For Me", "Muni Long"),
        ("Texas Hold 'Em", "Beyonce"),
        ("Beautiful Things", "Benson Boone"),
        ("Lose Control", "Teddy Swims"),
        ("Stick Season", "Noah Kahan"),
        ("Unholy", "Sam Smith & Kim Petras"),
        ("I Ain't Worried", "OneRepublic"),
        ("About Damn Time", "Lizzo"),
        ("Late Night Talking", "Harry Styles"),
        ("Satellite", "Harry Styles"),
        ("Chemical", "Post Malone"),
    ],
}


def _track_key(track_name: str | None, artist_name: str | None) -> RecommendationKey | None:
    if not track_name or not artist_name:
        return None
    return (track_name.strip().lower(), artist_name.strip().lower())


def _stable_track_id(prefix: str, track_name: str, artist_name: str) -> str:
    raw = f"{track_name}-{artist_name}".lower().encode("utf-8")
    return f"{prefix}_{hashlib.md5(raw).hexdigest()[:10]}"


def _generate_with_gemini(prompt: str, temperature: float = 0.7) -> str:
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
            "temperature": temperature,
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

    track_name = str(track_name).strip()
    artist_name = str(artist_name).strip()
    if _looks_invalid(track_name) or _looks_invalid(artist_name):
        print(f"[recommendations] filtered invalid track: {track_name} - {artist_name}")
        return None

    return {
        "track_name": track_name,
        "artist_name": artist_name,
        "reason": str(item.get("reason", "")),
        "source": str(item.get("source", "new")).lower(),
    }


def _looks_invalid(value: str) -> bool:
    if any(0x4E00 <= ord(char) <= 0x9FFF for char in value):
        return True
    mojibake_patterns = ("Ã", "Â", "Å", "æ", "ç", "é")
    return any(pattern in value for pattern in mojibake_patterns)


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
        match = re.search(r"\{.*\}", cleaned, re.DOTALL) or re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise ValueError("Gemini returned invalid recommendation JSON")
        parsed_json = json.loads(match.group(0))

    recommendations = [
        normalized
        for item in _extract_recommendation_items(parsed_json)[:20]
        if (normalized := _normalize_track(item))
    ]
    if not recommendations:
        raise ValueError("Gemini returned no usable recommendations")
    return recommendations


def _fetch_internet_context(genre_str: str) -> str:
    try:
        DDGS = importlib.import_module("ddgs").DDGS
        results = DDGS().text(
            f"trending {genre_str} artists 2024 2025 who are popular now",
            max_results=8,
        )
        if results:
            return "\n".join(f"- {result['title']}" for result in results)[:1000]
    except Exception as exc:
        print(f"[recommendations] internet context unavailable: {exc}")
    return "No internet context available."


def _genre_seed_recommendations(
    genre_seeds: list[str],
    exclude_keys: set[RecommendationKey] | None = None,
    limit: int = 20,
) -> list[dict]:
    exclude_keys = exclude_keys or set()
    picks = list(_seed_pool_for_genres(genre_seeds))
    random.shuffle(picks)

    results: list[dict] = []
    for track_name, artist_name in picks:
        key = _track_key(track_name, artist_name)
        if key in exclude_keys:
            continue
        index = len(results)
        results.append({
            "spotify_track_id": _stable_track_id("seed", track_name, artist_name),
            "track_name": track_name,
            "artist_name": artist_name,
            "score": max(0.1, 1.0 - index * 0.04),
        })
        if len(results) >= limit:
            break

    return results


def _seed_pool_for_genres(genre_seeds: list[str]) -> Iterable[tuple[str, str]]:
    genre_text = " ".join(genre_seeds).lower()
    if any(term in genre_text for term in ("electronic", "edm", "dance")):
        return _GENRE_SEEDS["electronic"]
    if any(term in genre_text for term in ("hip", "rap")):
        return _GENRE_SEEDS["hiphop"]
    if "pop" in genre_text:
        return _GENRE_SEEDS["pop"]

    combined: list[tuple[str, str]] = []
    for genre in ("electronic", "pop", "hiphop"):
        combined.extend(_GENRE_SEEDS[genre])
    return combined


async def _load_session_context(session_id: uuid.UUID, db: AsyncSession) -> dict | None:
    session_result = await db.execute(select(DBSession).where(DBSession.id == session_id))
    db_session = session_result.scalar_one_or_none()
    if not db_session:
        return None

    playlist_rows = (await db.execute(text("""
        SELECT track_name, artist_name
        FROM playlist_tracks
        WHERE session_id = :session_id
    """), {"session_id": session_id})).fetchall()

    previous_rows = (await db.execute(text("""
        SELECT track_name, artist_name
        FROM recommendations
        WHERE session_id = :session_id
    """), {"session_id": session_id})).fetchall()

    guest_rows = (await db.execute(text("""
        SELECT
            gt.track_name, gt.artist_name, gt.popularity,
            gt.danceability, gt.energy, gt.valence,
            gt.tempo, gt.acousticness, gt.instrumentalness,
            g.display_name
        FROM guest_tracks gt
        JOIN guests g ON gt.guest_id = g.id
        WHERE g.session_id = :session_id
    """), {"session_id": session_id})).fetchall()

    guest_count = (await db.execute(text(
        "SELECT COUNT(DISTINCT id) FROM guests WHERE session_id = :session_id"
    ), {"session_id": session_id})).scalar() or 0

    excluded_rows = [*playlist_rows, *previous_rows]
    excluded_lines = [
        f"{row.track_name} - {row.artist_name}"
        for row in excluded_rows
        if row.track_name and row.artist_name
    ]
    exclude_keys = {
        key
        for row in excluded_rows
        if (key := _track_key(row.track_name, row.artist_name))
    }

    return {
        "session": db_session,
        "genre_seeds": db_session.genre_seeds or [],
        "guest_rows": guest_rows,
        "guest_count": guest_count,
        "excluded_text": "\n".join(excluded_lines) if excluded_lines else "None",
        "exclude_keys": exclude_keys,
    }


def _audio_summary(rows) -> str:
    features = ("danceability", "energy", "valence", "tempo", "acousticness", "instrumentalness")
    parts: list[str] = []
    for feature in features:
        values = [_safe_float(getattr(row, feature, None)) for row in rows]
        values = [value for value in values if value is not None]
        if values:
            parts.append(f"{feature.capitalize()}: {sum(values) / len(values):.2f}")
    return ", ".join(parts) if parts else "No audio data available"


def _safe_float(value, default=None):
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _guest_taste_summary(rows) -> str:
    guest_tracks: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        guest_name = row.display_name or "Guest"
        guest_tracks[guest_name].append(f"{row.track_name} - {row.artist_name}")

    lines = []
    for guest_name, tracks in guest_tracks.items():
        lines.append(f"Guest '{guest_name}' likes: " + ", ".join(tracks[:20]))
    return "\n".join(lines) if lines else "No guest tracks submitted yet."


def _build_prompt(
    genre_str: str,
    internet_context: str,
    guest_summary: str,
    audio_summary: str,
    excluded_text: str,
    cold_start: bool,
) -> str:
    context_line = (
        "Use the existing guest taste as light inspiration, but do not repeat submitted tracks."
        if cold_start
        else "Use the crowd audio profile and guest taste to shape the recommendations."
    )

    return f"""You are an elite, modern DJ assistant.

DJ's set genre(s): {genre_str}

TRENDING ARTISTS CONTEXT:
{internet_context}

CROWD AUDIO PROFILE:
{audio_summary}

GUEST TASTE:
{guest_summary}

ALREADY USED OR CURRENTLY RECOMMENDED (DO NOT RECOMMEND AGAIN):
{excluded_text}

{context_line}

Recommend exactly 20 real individual songs suitable for a live party.

Requirements:
- Exactly 10 songs in new_hits.
- Exactly 10 songs in guest_picks.
- All songs must match the DJ's set genres.
- Do not repeat anything in the already-used list.
- Do not invent songs, artists, albums, playlists, or placeholders.
- Prefer songs released after 2020 unless an older track is still highly useful.
- Use English / Latin characters only.
- Every song must appear once across both lists.

Return exactly one JSON object matching the configured schema.
Use only the keys new_hits, guest_picks, track_name, artist_name, and reason."""


async def recompute(session_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Regenerate and store recommendations for a session."""
    print(f"[recommendations] recompute session={session_id}")
    context = await _load_session_context(session_id, db)
    if not context:
        return []

    rows = context["guest_rows"]
    genre_seeds = context["genre_seeds"]
    genre_str = ", ".join(genre_seeds) if genre_seeds else "any suitable party genre"
    cold_start = not rows or context["guest_count"] < get_settings().COLD_START_THRESHOLD

    try:
        internet_context = _fetch_internet_context(genre_str)
        prompt = _build_prompt(
            genre_str=genre_str,
            internet_context=internet_context,
            guest_summary=_guest_taste_summary(rows),
            audio_summary=_audio_summary(rows),
            excluded_text=context["excluded_text"],
            cold_start=cold_start,
        )
        raw_response = _generate_with_gemini(prompt, temperature=0.7 if cold_start else 0.35)
        recommendations = _filter_recommendations(
            _parse_llm_recommendations(raw_response),
            exclude_keys=context["exclude_keys"],
        )
    except Exception as exc:
        print(f"[recommendations] Gemini unavailable, using genre seeds: {exc}")
        recommendations = []

    if not recommendations:
        recommendations = _genre_seed_recommendations(
            genre_seeds,
            exclude_keys=context["exclude_keys"],
        )

    return await _save_recommendations(
        session_id=session_id,
        top_n=_to_ranked_items(recommendations[:20], cold_start=cold_start),
        db=db,
        guest_count=context["guest_count"],
        is_cold_start=cold_start,
    )


def _filter_recommendations(items: list[dict], exclude_keys: set[RecommendationKey]) -> list[dict]:
    filtered: list[dict] = []
    seen = set(exclude_keys)
    for item in items:
        key = _track_key(item.get("track_name"), item.get("artist_name"))
        if not key or key in seen:
            continue
        seen.add(key)
        filtered.append(item)
    return filtered


def _to_ranked_items(items: list[dict], cold_start: bool) -> list[dict]:
    ranked: list[dict] = []
    for index, item in enumerate(items):
        track_name = item.get("track_name", "Unknown Track")
        artist_name = item.get("artist_name", "Unknown Artist")
        source = item.get("source", "new")
        prefix = "llm_cold" if cold_start else "llm"
        ranked.append({
            "spotify_track_id": f"{prefix}_{source}_{hashlib.md5(f'{track_name}-{artist_name}'.lower().encode('utf-8')).hexdigest()[:10]}",
            "track_name": track_name,
            "artist_name": artist_name,
            "score": max(0.1, 1.0 - index * 0.04),
        })
    return ranked


async def _save_recommendations(
    session_id: uuid.UUID,
    top_n: list[dict],
    db: AsyncSession,
    guest_count: int,
    is_cold_start: bool,
) -> list[dict]:
    if not top_n:
        return []

    await db.execute(delete(Recommendation).where(Recommendation.session_id == session_id))

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
