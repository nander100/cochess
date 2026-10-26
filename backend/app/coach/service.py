"""Coach orchestration: generate, validate, and store the synopsis (SPEC §7)."""

import logging
from dataclasses import dataclass, replace

from anthropic.types import MessageParam
from sqlalchemy.orm import Session, sessionmaker

from app.coach.client import CoachClient, CoachReply, CoachRequest, system_blocks
from app.coach.payload import SYNOPSIS_INSTRUCTION, build_synopsis_payload, render
from app.coach.validate import allowed_moves, find_invalid, strip_moves
from app.config import Settings
from app.db.coach import load_synopsis, record_usage, save_synopsis
from app.db.engine_results import load_summary
from app.db.models import Game

logger = logging.getLogger(__name__)

REGENERATE_NOTE = (
    "Your synopsis mentioned moves that are not in the data: {moves}. Rewrite the complete "
    "synopsis. Only write moves exactly as they appear in the JSON, and describe pieces and "
    "squares in words."
)


@dataclass(frozen=True)
class SynopsisResult:
    text: str
    invalid_moves_removed: list[str]


async def generate_synopsis(
    client: CoachClient, settings: Settings, sessions: sessionmaker[Session], game_id: str
) -> SynopsisResult:
    """The stored synopsis if there is one; otherwise a new one, validated per SPEC §7.4:
    regenerate once with a note listing invalid moves, then remove any that remain."""
    with sessions() as session:
        stored = load_synopsis(session, game_id)
        if stored is not None:
            return SynopsisResult(*stored)
        game = session.get(Game, game_id)
        summary = load_summary(session, game_id)
        if game is None or summary is None:
            raise LookupError(f"game {game_id} has no summary yet")
    payload = build_synopsis_payload(summary, settings.coach)
    allowed = allowed_moves(payload.model_dump(mode="json"))
    messages: list[MessageParam] = [
        {"role": "user", "content": render(payload, SYNOPSIS_INSTRUCTION)}
    ]
    request = CoachRequest(
        model=settings.coach_model_synopsis,
        system=system_blocks("synopsis"),
        messages=messages,
        max_tokens=settings.coach.synopsis_max_tokens,
        effort=settings.coach.synopsis_effort,
    )

    reply = await _call(client, request, sessions, game_id)
    invalid = find_invalid(reply.text, allowed)
    if invalid:
        retry: list[MessageParam] = [
            *messages,
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": REGENERATE_NOTE.format(moves=", ".join(invalid))},
        ]
        reply = await _call(client, replace(request, messages=retry), sessions, game_id)
        invalid = find_invalid(reply.text, allowed)

    text = reply.text
    if invalid:
        text = strip_moves(text, invalid)
        logger.warning("coach moves removed: game=%s endpoint=synopsis moves=%s", game_id, invalid)
    words = len(text.split())
    if words > settings.coach.synopsis_max_words:
        logger.warning("synopsis too long: game=%s words=%d", game_id, words)
    with sessions() as session:
        save_synopsis(session, game_id, text, invalid)
    return SynopsisResult(text=text, invalid_moves_removed=invalid)


async def _call(
    client: CoachClient, request: CoachRequest, sessions: sessionmaker[Session], game_id: str
) -> CoachReply:
    reply = await client.complete(request)
    with sessions() as session:
        record_usage(session, game_id, "synopsis", reply.model, reply.usage)
    return reply
