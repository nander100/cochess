"""Persistence for the coach: the stored synopsis and per-call token usage."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coach.client import Usage
from app.db.models import ChatMessageRow, Game, LlmUsageRow

SYNOPSIS = "synopsis"


def record_usage(
    session: Session,
    game_id: str | None,
    endpoint: str,
    model: str,
    usage: Usage,
    *,
    user_id: str | None = None,
) -> None:
    """One call's tokens, for the game's owner, or `user_id` for a call about no one game."""
    game = session.get(Game, game_id) if game_id is not None else None
    session.add(
        LlmUsageRow(
            game_id=game_id,
            user_id=game.user_id if game is not None else user_id,
            endpoint=endpoint,
            task=endpoint,  # v1's two endpoints are also the task names (SPEC_V2 §6.1)
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
        )
    )
    session.commit()


def save_synopsis(session: Session, game_id: str, text: str, removed: list[str]) -> None:
    content = {"type": SYNOPSIS, "text": text, "invalid_moves_removed": removed}
    session.add(ChatMessageRow(game_id=game_id, role="assistant", content=content))
    session.commit()


def load_synopsis(session: Session, game_id: str) -> tuple[str, list[str]] | None:
    """(text, moves removed) of the stored synopsis, if there is one."""
    rows = session.scalars(
        select(ChatMessageRow)
        .where(ChatMessageRow.game_id == game_id, ChatMessageRow.role == "assistant")
        .order_by(ChatMessageRow.id)
    )
    for row in rows:
        if row.content.get("type") == SYNOPSIS:
            return str(row.content["text"]), list(row.content.get("invalid_moves_removed", []))
    return None
