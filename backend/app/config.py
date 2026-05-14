"""Application settings loaded from environment variables."""

from functools import lru_cache
import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """CrowdBeat global settings."""

    # --- Spotify OAuth ---
    SPOTIFY_CLIENT_ID: str
    SPOTIFY_CLIENT_SECRET: str
    SPOTIFY_REDIRECT_URI: str = "http://127.0.0.1:8000/auth/callback"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/crowdbeat"

    # --- Frontend ---
    FRONTEND_URL: str = "http://localhost:5173"

    # --- Security ---
    SECRET_KEY: str = "change_me_to_a_random_string"

    # --- ML Engine ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # --- Recommendation tuning ---
    WEIGHT_DANCEABILITY: float = 0.25
    WEIGHT_ENERGY: float = 0.25
    WEIGHT_VALENCE: float = 0.20
    WEIGHT_TEMPO: float = 0.15
    WEIGHT_ACOUSTICNESS: float = 0.10
    WEIGHT_INSTRUMENTALNESS: float = 0.05
    COLD_START_THRESHOLD: int = 5
    RECOMMENDATION_LIMIT: int = 20

    model_config = {
        "env_file": os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()
