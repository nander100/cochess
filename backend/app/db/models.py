"""SQLAlchemy models. Every schema change goes through an Alembic migration (backend/alembic)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import UtcDateTime


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    # Named constraints, so Alembic batch migrations can drop and recreate them on SQLite.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class User(Base):
    """A player (SPEC_V2 §4.3). The profile fields stay empty until the first login."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(60))
    # Lower-cased name: names are unique ignoring case, because the CLI looks users up by name.
    name_key: Mapped[str] = mapped_column(String(60), unique=True)
    elo: Mapped[int | None] = mapped_column(Integer)
    time_control: Mapped[str | None] = mapped_column(String(10))
    playstyle: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_utcnow, onupdate=_utcnow)


class Invite(Base):
    """A one-time login link (SPEC_V2 §4.1). Only the token's hash is stored."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_utcnow)


class AuthSession(Base):
    """A logged-in browser. Only the cookie token's hash is stored."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_utcnow)


class Game(Base):
    __tablename__ = "games"

    __table_args__ = (Index("ix_games_user_id_played_at", "user_id", "played_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    # Null only for v1 games not yet given to a user (`cli assign-games`); those are invisible.
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    pgn: Mapped[str] = mapped_column(Text)
    user_color: Mapped[str] = mapped_column(String(5))
    elo: Mapped[int] = mapped_column(Integer)  # the player's Elo when the game was analyzed
    playstyle: Mapped[str | None] = mapped_column(Text)
    headers: Mapped[dict[str, str]] = mapped_column(JSON)
    time_control_category: Mapped[str | None] = mapped_column(String(10))
    user_result: Mapped[str | None] = mapped_column(String(4))  # win / loss / draw
    played_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    status: Mapped[str] = mapped_column(String(10), default="uploaded", server_default="uploaded")
    source: Mapped[str] = mapped_column(String(10), default="single", server_default="single")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_utcnow)


class EngineResultRow(Base):
    """One engine search of one position. `lines` holds the SPEC §5.4 lines, White POV."""

    __tablename__ = "engine_results"
    __table_args__ = (UniqueConstraint("game_id", "fen", "tier"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    # Browser results are only ever reused within the same user's data (SPEC_V2 §4.2).
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    ply: Mapped[int | None] = mapped_column(Integer)
    fen: Mapped[str] = mapped_column(String(100))
    tier: Mapped[str] = mapped_column(String(6))
    depth: Mapped[int] = mapped_column(Integer)
    time_ms: Mapped[int] = mapped_column(Integer)
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_utcnow)


class GameSummaryRow(Base):
    """The SPEC §6.5 game summary, rebuilt whenever verify results arrive."""

    __tablename__ = "game_summaries"

    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_utcnow)


class ChatMessageRow(Base):
    """The coach conversation for a game. `content` is JSON: the synopsis (M4), then chat turns
    as Anthropic content blocks (M5)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_utcnow)


class LlmUsageRow(Base):
    """One Claude API call's token usage (SPEC §7.1), for v4 credit metering."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str | None] = mapped_column(ForeignKey("games.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint: Mapped[str] = mapped_column(String(32))
    # SPEC_V2 §6.1 task: synopsis, chat, explain, moment_intro, moment_feedback, baseline_report
    task: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cache_read_tokens: Mapped[int] = mapped_column(Integer)
    cache_write_tokens: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_utcnow)


class PendingToolCallRow(Base):
    """An analyze_position call waiting for the browser's deep-dive results (SPEC §8.3)."""

    __tablename__ = "pending_tool_calls"

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    tool_use: Mapped[dict[str, Any]] = mapped_column(JSON)  # {"id": ..., "input": {...}}
    positions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # tool_result blocks for any other tool_use blocks in the same turn (answered with errors)
    extra_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    tool_calls_used: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_utcnow)
