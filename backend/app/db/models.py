"""SQLAlchemy models (SPEC §9.1). Tables leave room for a nullable `user_id` column in v2."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    pgn: Mapped[str] = mapped_column(Text)
    user_color: Mapped[str] = mapped_column(String(5))
    elo: Mapped[int] = mapped_column(Integer)
    playstyle: Mapped[str | None] = mapped_column(Text)
    headers: Mapped[dict[str, str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EngineResultRow(Base):
    """One engine search of one position. `lines` holds the SPEC §5.4 lines, White POV."""

    __tablename__ = "engine_results"
    __table_args__ = (UniqueConstraint("game_id", "fen", "tier"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    ply: Mapped[int | None] = mapped_column(Integer)
    fen: Mapped[str] = mapped_column(String(100))
    tier: Mapped[str] = mapped_column(String(6))
    depth: Mapped[int] = mapped_column(Integer)
    time_ms: Mapped[int] = mapped_column(Integer)
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GameSummaryRow(Base):
    """The SPEC §6.5 game summary, rebuilt whenever verify results arrive."""

    __tablename__ = "game_summaries"

    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ChatMessageRow(Base):
    """The coach conversation for a game. `content` is JSON: the synopsis (M4), then chat turns
    as Anthropic content blocks (M5)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class LlmUsageRow(Base):
    """One Claude API call's token usage (SPEC §7.1), for v4 credit metering."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str | None] = mapped_column(ForeignKey("games.id"), index=True)
    endpoint: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cache_read_tokens: Mapped[int] = mapped_column(Integer)
    cache_write_tokens: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
