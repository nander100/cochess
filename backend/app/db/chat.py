"""Persistence for chat: the conversation as Anthropic content blocks, and pending tool calls.

Rows with content {"type": "chat", "blocks": [...]} are replayed to Claude in order; the stored
synopsis row ({"type": "synopsis"}) isn't (it goes into the cached game context instead).
"""

import json
from typing import Any, Literal, cast

from anthropic.types import MessageParam
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChatMessageRow, PendingToolCallRow

CHAT = "chat"


def save_turn(
    session: Session,
    game_id: str,
    role: str,
    blocks: list[dict[str, Any]],
    *,
    display: str | None = None,
    where: str | None = None,
    path_uci: list[str] | None = None,
) -> None:
    """Store one turn. A player's turn also keeps the plain message (`display`), where on the board
    it was asked (`where`, e.g. "after 14. Nf3"), and that position's path."""
    content: dict[str, Any] = {"type": CHAT, "blocks": blocks}
    if display is not None:
        content["display"] = display
    if where is not None:
        content["where"] = where
    session.add(ChatMessageRow(game_id=game_id, role=role, content=content, path_uci=path_uci))
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


class ChatEntry(BaseModel):
    """A chat message as the player sees it in the history."""

    role: Literal["player", "coach"]
    text: str
    where: str | None = None  # the board position a player's message was sent from


def chat_history(session: Session, game_id: str) -> list[ChatEntry]:
    """The conversation for display: the player's messages and the coach's final answers.

    Tool calls, tool results and thinking are internal and left out. The player's message is
    stored inside the rendered payload (an instruction line, then JSON with `user_prompt`).
    """
    entries: list[ChatEntry] = []
    for row in _chat_rows(session, game_id):
        blocks = row.content["blocks"]
        texts = [str(b.get("text", "")) for b in blocks if b.get("type") == "text"]
        if not texts:
            continue
        if row.role == "user":
            # v2 rows keep the plain message; v1 rows only have it inside the payload.
            prompt = row.content.get("display") or _player_prompt(texts[0])
            if prompt is not None:
                where = row.content.get("where")
                entries.append(ChatEntry(role="player", text=prompt, where=where))
        elif not any(b.get("type") == "tool_use" for b in blocks):
            entries.append(ChatEntry(role="coach", text="".join(texts)))
    return entries


def _player_prompt(rendered: str) -> str | None:
    _, _, payload = rendered.partition("\n\n")
    try:
        prompt = json.loads(payload).get("user_prompt")
    except (json.JSONDecodeError, AttributeError):
        return None
    return prompt if isinstance(prompt, str) else None


def user_payloads(session: Session, game_id: str) -> list[Any]:
    """The JSON payload of every player turn (instruction line, blank line, JSON), for validation:
    a move the coach was shown in an earlier turn is still a move from the data."""
    payloads = []
    for row in _chat_rows(session, game_id):
        if row.role != "user":
            continue
        for block in row.content["blocks"]:
            if block.get("type") != "text":
                continue
            _, _, payload = str(block.get("text", "")).partition("\n\n")
            try:
                payloads.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
    return payloads


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
