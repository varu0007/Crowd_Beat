"""
database.py — SQLAlchemy 2.0 异步模型定义
包含 4 张表: sessions, guests, guest_tracks, recommendations
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    String,
    Text,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from app.config import get_settings


# ────────────────────────────────────────────
# Base
# ────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ────────────────────────────────────────────
# Models
# ────────────────────────────────────────────

class Session(Base):
    """DJ 活动场次"""
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    host_spotify_id: Mapped[Optional[str]] = mapped_column(String(100))
    genre_seeds: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    guests: Mapped[List["Guest"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    recommendations: Mapped[List["Recommendation"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    playlist_tracks: Mapped[List["PlaylistTrack"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

class PlaylistTrack(Base):
    """DJ 内部虚拟歌单记录"""
    __tablename__ = "playlist_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    spotify_track_id: Mapped[str] = mapped_column(String(100), nullable=False)
    track_name: Mapped[Optional[str]] = mapped_column(String(300))
    artist_name: Mapped[Optional[str]] = mapped_column(String(300))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="playlist_tracks")

    __table_args__ = (
        Index("ix_playlist_tracks_session_id", "session_id"),
    )



class Guest(Base):
    """扫码加入的观众"""
    __tablename__ = "guests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    spotify_user_id: Mapped[Optional[str]] = mapped_column(String(100))
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(Text)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="guests")
    tracks: Mapped[List["GuestTrack"]] = relationship(
        back_populates="guest", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_guests_session_id", "session_id"),
    )


class GuestTrack(Base):
    """观众的 top tracks + audio features"""
    __tablename__ = "guest_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guests.id", ondelete="CASCADE")
    )
    spotify_track_id: Mapped[str] = mapped_column(String(100), nullable=False)
    track_name: Mapped[Optional[str]] = mapped_column(String(300))
    artist_name: Mapped[Optional[str]] = mapped_column(String(300))

    # Audio features (0.0 ~ 1.0, except tempo which is BPM)
    danceability: Mapped[Optional[float]] = mapped_column(Float)
    energy: Mapped[Optional[float]] = mapped_column(Float)
    valence: Mapped[Optional[float]] = mapped_column(Float)
    tempo: Mapped[Optional[float]] = mapped_column(Float)
    acousticness: Mapped[Optional[float]] = mapped_column(Float)
    instrumentalness: Mapped[Optional[float]] = mapped_column(Float)
    popularity: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    guest: Mapped["Guest"] = relationship(back_populates="tracks")

    __table_args__ = (
        Index("ix_guest_tracks_guest_id", "guest_id"),
        Index("ix_guest_tracks_spotify_track_id", "spotify_track_id"),
    )


class Recommendation(Base):
    """推荐结果快照"""
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    spotify_track_id: Mapped[str] = mapped_column(String(100), nullable=False)
    track_name: Mapped[Optional[str]] = mapped_column(String(300))
    artist_name: Mapped[Optional[str]] = mapped_column(String(300))
    score: Mapped[Optional[float]] = mapped_column(Float)
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    guest_count: Mapped[Optional[int]] = mapped_column(Integer)
    is_cold_start: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="recommendations")


# ────────────────────────────────────────────
# Async Engine & Session Factory
# ────────────────────────────────────────────

_engine = None
_async_session_factory = None


def get_engine():
    """获取或创建 async engine（延迟初始化）"""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_factory():
    """获取或创建 async session factory"""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_db():
    """FastAPI 依赖注入：提供数据库 session"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """创建所有表（首次启动时调用）"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """关闭数据库连接池"""
    global _engine, _async_session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
