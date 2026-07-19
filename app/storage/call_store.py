"""
Durable storage for completed calls and post-call analysis.

Tables are created automatically on application startup when ``DATABASE_ENABLED``
is true. Supports PostgreSQL (Docker) and SQLite (local dev).

Example::

    await init_database()
    async with get_db() as session:
        session.add(Conversation(id="abc-123", status="live"))
        await session.commit()
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

JsonColumn = JSON

# Module-level connection state (set by init_database, cleared by close_database).
db_engine = None
db_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    """One live or completed sales call."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="live", index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lead_speaker_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    audio_channels: Mapped[int] = mapped_column(Integer, default=1)
    workspace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    rep_label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JsonColumn, default=dict)

    segments: Mapped[list["TranscriptSegmentRow"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    suggestions: Mapped[list["SuggestionRow"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["ConversationAnalysis"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class TranscriptSegmentRow(Base):
    """One finalized speech span from a single speaker."""

    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    speaker_id: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(12), default="unknown")
    start_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)

    conversation: Mapped["Conversation"] = relationship(back_populates="segments")


class SuggestionRow(Base):
    """One AI coaching suggestion shown during a call."""

    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    generation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trigger_query: Mapped[str] = mapped_column(Text, default="")
    suggestion_text: Mapped[str] = mapped_column(Text, default="")
    from_cache: Mapped[bool] = mapped_column(default=False)
    sources: Mapped[list[Any]] = mapped_column(JsonColumn, default=list)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="suggestions")


class ConversationAnalysis(Base):
    """Structured post-call report and deterministic metrics for one run."""

    __tablename__ = "conversation_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    model: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    metrics: Mapped[dict[str, Any]] = mapped_column(JsonColumn, default=dict)
    analysis: Mapped[dict[str, Any]] = mapped_column(JsonColumn, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="analyses")


class KnowledgeSource(Base):
    """User-uploaded file indexed into Qdrant for RAG."""

    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(12))
    file_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="processing", index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


def database_enabled() -> bool:
    """
    Return whether call persistence is turned on.

    Example::

        if database_enabled():
            await init_database()
    """
    return bool(settings.DATABASE_URL and settings.DATABASE_ENABLED)


def create_db_engine():
    """
    Build an async SQLAlchemy engine from ``DATABASE_URL``.

    Normalizes common URL forms, e.g. ``postgresql://`` becomes
    ``postgresql+asyncpg://``, and plain ``sqlite://`` becomes ``sqlite+aiosqlite://``.

    Example::

        engine = create_db_engine()
        # settings.DATABASE_URL = "sqlite+aiosqlite:///./data/calls.db"
    """
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("sqlite://") and "aiosqlite" not in url:
        url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return create_async_engine(url, echo=False)


async def init_database() -> None:
    """
    Connect to the database and create tables if they do not exist.

    Safe to call on every app startup. No-op when persistence is disabled.

    Example::

        # In FastAPI lifespan
        await init_database()
    """
    global db_engine, db_session_factory
    if not database_enabled():
        logger.info("Call persistence disabled (DATABASE_ENABLED=false or no DATABASE_URL)")
        return
    url = settings.DATABASE_URL
    if "sqlite" in url:
        Path("data").mkdir(parents=True, exist_ok=True)
    db_engine = create_db_engine()
    db_session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Call database ready")


async def close_database() -> None:
    """
    Dispose the database engine on application shutdown.

    Example::

        await close_database()
    """
    global db_engine, db_session_factory
    if db_engine is not None:
        await db_engine.dispose()
    db_engine = None
    db_session_factory = None


@asynccontextmanager
async def get_db() -> AsyncIterator[AsyncSession]:
    """
    Yield one async database session for a single unit of work.

    Example::

        async with get_db() as session:
            row = await session.get(Conversation, conversation_id)
    """
    if db_session_factory is None:
        raise RuntimeError("Database is not initialized")
    async with db_session_factory() as session:
        yield session


async def next_analysis_version(session: AsyncSession, conversation_id: str) -> int:
    """
    Return the next analysis version number for a conversation (1, 2, 3, …).

    Used when the user clicks re-analyze so older reports are kept.

    Example::

        version = await next_analysis_version(session, "abc-123")  # -> 2 after first run
    """
    result = await session.execute(
        select(func.max(ConversationAnalysis.version)).where(
            ConversationAnalysis.conversation_id == conversation_id
        )
    )
    current = result.scalar()
    return int(current or 0) + 1
