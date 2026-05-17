"""CrowdBeat module."""

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
    text,
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


# ---
# Base
# ---

class Base(DeclarativeBase):
    pass


# ---
# Models
# ---

class Session(Base):
    """Internal helper."""
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
    """Internal helper."""
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
    """Internal helper."""
    __tablename__ = "guests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    spotify_user_id: Mapped[Optional[str]] = mapped_column(String(100))
    spotify_username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="approved")
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
    """Internal helper."""
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
    """Internal helper."""
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


class GuestInfo(Base):
    """Stores guest details for manual whitelisting."""
    __tablename__ = "guest_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True
    )
    username: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

# ---
# Async Engine & Session Factory
# ---

_engine = None
_async_session_factory = None


def get_engine():
    """Internal helper."""
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
    """Internal helper."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_db():
    """Internal helper."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Internal helper."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_schema_compatibility(conn)


async def _ensure_schema_compatibility(conn):
    """Apply tiny schema repairs for local databases created before model changes."""
    dialect_name = conn.dialect.name
    if dialect_name != "postgresql":
        return

    missing_guest_email = await conn.scalar(text("""
        SELECT NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'guests'
              AND column_name = 'email'
        )
    """))
    if missing_guest_email:
        await conn.execute(text("ALTER TABLE guests ADD COLUMN email VARCHAR(200)"))

    missing_spotify_username = await conn.scalar(text("""
        SELECT NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'guests'
              AND column_name = 'spotify_username'
        )
    """))
    if missing_spotify_username:
        await conn.execute(text("ALTER TABLE guests ADD COLUMN spotify_username VARCHAR(200)"))

    missing_approval_status = await conn.scalar(text("""
        SELECT NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'guests'
              AND column_name = 'approval_status'
        )
    """))
    if missing_approval_status:
        await conn.execute(text("""
            ALTER TABLE guests
            ADD COLUMN approval_status VARCHAR(20) NOT NULL DEFAULT 'approved'
        """))


async def close_db():
    """Internal helper."""
    global _engine, _async_session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
