"""
config.py — 应用配置
使用 pydantic-settings 从 .env 文件加载环境变量
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    """CrowdBeat 全局配置"""

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

    # 推荐算法特征权重
    WEIGHT_DANCEABILITY: float = 0.25
    WEIGHT_ENERGY: float = 0.25
    WEIGHT_VALENCE: float = 0.20
    WEIGHT_TEMPO: float = 0.15
    WEIGHT_ACOUSTICNESS: float = 0.10
    WEIGHT_INSTRUMENTALNESS: float = 0.05

    # Cold start 阈值
    COLD_START_THRESHOLD: int = 5

    # 推荐返回数量
    RECOMMENDATION_LIMIT: int = 20

    model_config = {
        "env_file": os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """缓存的 Settings 实例，全局单例"""
    return Settings()
