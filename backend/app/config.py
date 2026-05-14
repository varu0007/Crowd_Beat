"""
config.py â€” åº”ç”¨é…ç½®
ä½¿ç”¨ pydantic-settings ä»Ž .env æ–‡ä»¶åŠ è½½çŽ¯å¢ƒå˜é‡
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    """CrowdBeat å…¨å±€é…ç½®"""

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

    # æŽ¨èç®—æ³•ç‰¹å¾æƒé‡
    WEIGHT_DANCEABILITY: float = 0.25
    WEIGHT_ENERGY: float = 0.25
    WEIGHT_VALENCE: float = 0.20
    WEIGHT_TEMPO: float = 0.15
    WEIGHT_ACOUSTICNESS: float = 0.10
    WEIGHT_INSTRUMENTALNESS: float = 0.05

    # Cold start é˜ˆå€¼
    COLD_START_THRESHOLD: int = 5

    # æŽ¨èè¿”å›žæ•°é‡
    RECOMMENDATION_LIMIT: int = 20

    model_config = {
        "env_file": os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """ç¼“å­˜çš„ Settings å®žä¾‹ï¼Œå…¨å±€å•ä¾‹"""
    return Settings()
