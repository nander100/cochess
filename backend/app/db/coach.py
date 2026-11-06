"""Persistence for the coach: the stored synopsis and per-call token usage."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.coach.client import Usage
from app.coach.markup import MessageTokens
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


@dataclass(frozen=True)
class StoredText:
    """A stored coach text: as the player sees it (`text`, with placeholders), as the coach wrote
    it (`raw`, valid tags as markup, for later prompts), and its tokens (SPEC_V3 §11.2)."""

    text: str
    raw: str
    invalid_moves_removed: list[str]
    tokens: MessageTokens


def save_synopsis(session: Session, game_id: str, stored: StoredText) -> None:
    content = {
        "type": SYNOPSIS,
        "text": stored.text,
        "raw": stored.raw,
        "invalid_moves_removed": stored.invalid_moves_removed,
        **stored.tokens.model_dump(mode="json"),
    }
    session.add(ChatMessageRow(game_id=game_id, role="assistant", content=content))
    session.commit()


def load_synopsis(session: Session, game_id: str) -> StoredText | None:
    """The stored synopsis, if there is one (v2 synopses have no raw text or tokens)."""
    rows = session.scalars(
        select(ChatMessageRow)
        .where(ChatMessageRow.game_id == game_id, ChatMessageRow.role == "assistant")
        .order_by(ChatMessageRow.id)
    )
    for row in rows:
        content = row.content
        if content.get("type") == SYNOPSIS:
            return StoredText(
                text=str(content["text"]),
                raw=str(content.get("raw", content["text"])),
                invalid_moves_removed=list(content.get("invalid_moves_removed", [])),
                tokens=MessageTokens.model_validate(content),
            )
    return None


def tokens_used_since(session: Session, user_id: str, since: datetime) -> int:
    """All of a player's Claude tokens since `since`: input, output, and cache reads and writes."""
    total = session.scalar(
        select(
            func.coalesce(
                func.sum(
                    LlmUsageRow.input_tokens
                    + LlmUsageRow.output_tokens
                    + LlmUsageRow.cache_read_tokens
                    + LlmUsageRow.cache_write_tokens
                ),
                0,
            )
        ).where(LlmUsageRow.user_id == user_id, LlmUsageRow.created_at >= since)
    )
    return int(total or 0)
