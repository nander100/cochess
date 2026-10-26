"""SQLAlchemy models (SPEC §9.1). Tables leave room for a nullable `user_id` column in v2."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
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
