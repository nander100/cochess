"""Coach orchestration: generate, validate, and store the synopsis (SPEC §7)."""

import logging
from dataclasses import dataclass, field, replace

from anthropic.types import MessageParam
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.pgn import parse_pgn
from app.coach.client import CoachClient, CoachReply, CoachRequest, system_blocks
from app.coach.lines import key_moment_lines
from app.coach.markup import MessageTokens, Rules, note, process
from app.coach.payload import (
    SYNOPSIS_INSTRUCTION,
    build_synopsis_payload,
    player_payload,
    render,
    with_tendencies,
)
from app.coach.validate import allowed_moves
from app.config import Settings
from app.db.annotations import log_dropped
from app.db.coach import StoredText, load_synopsis, record_usage, save_synopsis
from app.db.engine_results import load_summary
from app.db.line_links import save_line_links
from app.db.models import Game
from app.db.tendencies import latest_tendencies
from app.db.user_settings import detail_level_for

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
    tokens: MessageTokens = field(default_factory=MessageTokens)


async def generate_synopsis(
    client: CoachClient, settings: Settings, sessions: sessionmaker[Session], game_id: str
) -> SynopsisResult:
    """The stored synopsis if there is one; otherwise a new one, validated per SPEC §7.4:
    regenerate once with a note listing invalid moves, then remove any that remain."""
    with sessions() as session:
        stored = load_synopsis(session, game_id)
        if stored is not None:
            return SynopsisResult(stored.text, stored.invalid_moves_removed, stored.tokens)
        game = session.get(Game, game_id)
        summary = load_summary(session, game_id)
        if game is None or summary is None:
            raise LookupError(f"game {game_id} has no summary yet")
        report = latest_tendencies(session, game.user_id) if game.user_id else None
        detail = detail_level_for(session, game.user_id)
        user_id = game.user_id
        parsed = parse_pgn(
            game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
        )
    lines = key_moment_lines(parsed, summary, settings.coach.line_link_max_plies)
    player = with_tendencies(player_payload(summary, detail), report, settings.tendencies)
    payload = build_synopsis_payload(summary, settings.coach, player)
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

    # The synopsis is about the whole game, not one board position: no board tags. Its line
    # links name the key moments (km<N>).
    rules = Rules(
        allowed=frozenset(allowed), limits=settings.coach, lines=lines,
        words_only_evals=player.detail_level == "plain", puzzles=settings.puzzles,
    )  # fmt: skip
    reply = await _call(client, request, sessions, game_id)
    done = process(reply.text, rules)
    if done.problems.any:
        retry: list[MessageParam] = [
            *messages,
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": note(done.problems)},
        ]
        reply = await _call(client, replace(request, messages=retry), sessions, game_id)
        done = process(reply.text, rules)
    if done.removed:
        logger.warning(
            "coach moves removed: game=%s endpoint=synopsis moves=%s", game_id, done.removed
        )
    words = len(done.text.split())
    if words > settings.coach.synopsis_max_words:
        logger.warning("synopsis too long: game=%s words=%d", game_id, words)
    stored = StoredText(
        text=done.text, raw=done.raw, invalid_moves_removed=done.removed, tokens=done.tokens
    )
    with sessions() as session:
        log_dropped(
            session, user_id=user_id, game_id=game_id, task="synopsis", dropped=done.dropped
        )
        if user_id is not None:
            save_line_links(session, user_id, game_id, "synopsis", done.line_links)
        save_synopsis(session, game_id, stored)
    return SynopsisResult(text=done.text, invalid_moves_removed=done.removed, tokens=done.tokens)


async def _call(
    client: CoachClient, request: CoachRequest, sessions: sessionmaker[Session], game_id: str
) -> CoachReply:
    reply = await client.complete(request)
    with sessions() as session:
        record_usage(session, game_id, "synopsis", reply.model, reply.usage)
    return reply
