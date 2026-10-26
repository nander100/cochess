"""Persistence for chat: the conversation as Anthropic content blocks, and pending tool calls.

Rows with content {"type": "chat", "blocks": [...]} are replayed to Claude in order; the stored
synopsis row ({"type": "synopsis"}) isn't (it goes into the cached game context instead).
"""

from typing import Any, cast

from anthropic.types import MessageParam
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChatMessageRow, PendingToolCallRow

CHAT = "chat"


def save_turn(session: Session, game_id: str, role: str, blocks: list[dict[str, Any]]) -> None:
    session.add(
        ChatMessageRow(game_id=game_id, role=role, content={"type": CHAT, "blocks": blocks})
    )
    session.commit()


def load_messages(session: Session, game_id: str) -> list[MessageParam]:
    """The conversation for the API, with consecutive same-role turns merged."""
    roles: list[str] = []
    contents: list[list[dict[str, Any]]] = []
    for row in _chat_rows(session, game_id):
        blocks = list(row.content["blocks"])
        if roles and roles[-1] == row.role:
            contents[-1].extend(blocks)
        else:
            roles.append(row.role)
            contents.append(blocks)
    # Stored blocks are the API's own JSON shapes, saved unchanged (thinking signatures too).
    return [
        cast(MessageParam, {"role": role, "content": content})
        for role, content in zip(roles, contents, strict=True)
    ]


def tool_results(session: Session, game_id: str) -> list[str]:
    """The content of every tool_result block in the conversation."""
    return [
        str(block.get("content", ""))
        for row in _chat_rows(session, game_id)
        for block in row.content["blocks"]
        if block.get("type") == "tool_result"
    ]


def count_player_messages(session: Session, game_id: str) -> int:
    """User turns that are the player's messages (not tool results)."""
    return sum(
        any(block.get("type") == "text" for block in row.content["blocks"])
        for row in _chat_rows(session, game_id)
        if row.role == "user"
    )


def save_pending(session: Session, pending: PendingToolCallRow) -> None:
    session.add(pending)
    session.commit()


def get_pending(session: Session, game_id: str, request_id: str) -> PendingToolCallRow | None:
    pending = session.get(PendingToolCallRow, request_id)
    return pending if pending is not None and pending.game_id == game_id else None


def pending_for_game(session: Session, game_id: str) -> PendingToolCallRow | None:
    return session.scalars(
        select(PendingToolCallRow).where(PendingToolCallRow.game_id == game_id)
    ).first()


def delete_pending(session: Session, pending: PendingToolCallRow) -> None:
    session.delete(pending)
    session.commit()


def _chat_rows(session: Session, game_id: str) -> list[ChatMessageRow]:
    rows = session.scalars(
        select(ChatMessageRow).where(ChatMessageRow.game_id == game_id).order_by(ChatMessageRow.id)
    )
    return [row for row in rows if row.content.get("type") == CHAT]
