"""Chat with the coach (SPEC §8): game context, history, the analyze_position round-trip, and the
same move validation as the synopsis (SPEC §7.4)."""

import contextlib
import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from anthropic.types import ContentBlock, MessageParam
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.engine import EngineResult, best_by_fen, check_batch
from app.analysis.pgn import ParsedGame, parse_pgn
from app.analysis.summary_models import GameSummary
from app.coach.client import CoachClient, CoachReply, CoachRequest, system_blocks
from app.coach.payload import CoachPayload, movetext, player_payload, render
from app.coach.tools import (
    ANALYZE_POSITION,
    EnginePosition,
    PositionRequest,
    ToolInputError,
    build_tool_result,
    parse_tool_input,
)
from app.coach.validate import allowed_moves, find_invalid, strip_moves
from app.config import Settings
from app.db.chat import (
    count_player_messages,
    delete_pending,
    get_pending,
    load_messages,
    pending_for_game,
    save_pending,
    save_turn,
    tool_results,
)
from app.db.coach import load_synopsis, record_usage
from app.db.engine_results import load_summary, save_results
from app.db.models import Game, PendingToolCallRow

logger = logging.getLogger(__name__)

CHAT_INSTRUCTION = (
    "The player's new chat message, as JSON. Answer it as described in your instructions."
)
CONTEXT_INTRO = "Context for this chat: the player's game and its analysis, as JSON."
CANCELLED = "The engine analysis was cancelled because the player sent a new message."
ONE_AT_A_TIME = "Only one position can be analyzed at a time. Ask again after this result."
REGENERATE_NOTE = (
    "Your answer mentioned moves that are not in the data: {moves}. Rewrite the complete "
    "answer. Only write moves that appear in the game data or the engine results, and describe "
    "pieces and squares in words."
)


class ChatLimitError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class PendingNotFoundError(Exception):
    """No analysis is waiting under that request id (finished, cancelled, or unknown)."""


@dataclass(frozen=True)
class FinalAnswer:
    text: str
    invalid_moves_removed: list[str]


@dataclass(frozen=True)
class EngineRequest:
    request_id: str
    positions: list[EnginePosition]


ChatOutcome = FinalAnswer | EngineRequest


@dataclass(frozen=True)
class _Context:
    game_id: str
    game: ParsedGame
    summary: GameSummary
    context_block: str
    allowed: frozenset[str]


async def send_message(
    client: CoachClient,
    settings: Settings,
    sessions: sessionmaker[Session],
    game_id: str,
    message: str,
) -> ChatOutcome:
    with sessions() as session:
        context = _load_context(session, settings, game_id)
        if count_player_messages(session, game_id) >= settings.coach.chat_max_messages:
            raise ChatLimitError(
                f"You've reached the limit of {settings.coach.chat_max_messages} questions "
                "for this game."
            )
        _cancel_pending(session, game_id)
        payload = CoachPayload(
            task="chat", user_prompt=message, player=player_payload(context.summary)
        )
        save_turn(session, game_id, "user", [_text(render(payload, CHAT_INSTRUCTION))])
    return await _loop(client, settings, sessions, context, tool_calls_used=0)


def check_engine_results(
    sessions: sessionmaker[Session],
    settings: Settings,
    game_id: str,
    request_id: str,
    results: Sequence[EngineResult],
) -> list[EngineResult]:
    """Validate deep-dive results against the pending request (raises before any streaming)."""
    with sessions() as session:
        pending = get_pending(session, game_id, request_id)
        if pending is None:
            raise PendingNotFoundError(request_id)
        expected = [p["fen"] for p in pending.positions]
    return check_batch(
        results, tier="deep", tier_config=settings.engine.deep, expected_fens=expected
    )


async def submit_engine_results(
    client: CoachClient,
    settings: Settings,
    sessions: sessionmaker[Session],
    game_id: str,
    request_id: str,
    results: Sequence[EngineResult],
) -> ChatOutcome:
    """Answer the pending tool call with the (already checked) results and resume the chat."""
    with sessions() as session:
        context = _load_context(session, settings, game_id)
        pending = get_pending(session, game_id, request_id)
        if pending is None:
            raise PendingNotFoundError(request_id)
        position = parse_tool_input(pending.tool_use["input"], context.game)
        save_results(session, game_id, results)
        result = build_tool_result(
            position, context.game, best_by_fen(results), settings.thresholds
        )
        blocks = [
            _tool_result(pending.tool_use["id"], result.model_dump_json()),
            *pending.extra_results,
        ]
        used = pending.tool_calls_used
        delete_pending(session, pending)
        save_turn(session, game_id, "user", blocks)
    return await _loop(client, settings, sessions, context, tool_calls_used=used)


async def _loop(
    client: CoachClient,
    settings: Settings,
    sessions: sessionmaker[Session],
    context: _Context,
    tool_calls_used: int,
) -> ChatOutcome:
    """Call Claude until it answers in text, or asks for an engine analysis the browser must run.

    Tool calls the backend can reject (bad ply, illegal move) are answered with an error right
    away; once the per-message limit is used up, Claude must answer without tools.
    """
    while True:
        request = _request(settings, sessions, context, tool_calls_used)
        reply = await _call(client, request, sessions, context.game_id)
        tool_uses = [block for block in reply.content if block.type == "tool_use"]
        if reply.stop_reason != "tool_use" or not tool_uses:
            return await _finish(client, settings, sessions, context, reply)

        tool_calls_used += len(tool_uses)
        with sessions() as session:
            save_turn(session, context.game_id, "assistant", _dump(reply.content))
        first, rest = tool_uses[0], tool_uses[1:]
        extra = [_tool_result(block.id, ONE_AT_A_TIME, error=True) for block in rest]
        try:
            position = parse_tool_input(first.input, context.game)
        except ToolInputError as error:
            with sessions() as session:
                blocks = [_tool_result(first.id, error.message, error=True), *extra]
                save_turn(session, context.game_id, "user", blocks)
            continue
        return _request_engine(
            sessions, context, first.id, first.input, position, extra, tool_calls_used
        )


def _request(
    settings: Settings, sessions: sessionmaker[Session], context: _Context, tool_calls_used: int
) -> CoachRequest:
    with sessions() as session:
        messages = load_messages(session, context.game_id)
    limit_reached = tool_calls_used >= settings.coach.chat_max_tool_calls
    return CoachRequest(
        model=settings.coach_model_chat,
        system=system_blocks(context.context_block),
        messages=messages,
        max_tokens=settings.coach.chat_max_tokens,
        effort=settings.coach.chat_effort,
        tools=[ANALYZE_POSITION],
        tool_choice={"type": "none"} if limit_reached else None,
    )


def _request_engine(
    sessions: sessionmaker[Session],
    context: _Context,
    tool_use_id: str,
    tool_input: object,
    position: PositionRequest,
    extra: list[dict[str, Any]],
    tool_calls_used: int,
) -> EngineRequest:
    request_id = str(uuid.uuid4())
    positions = position.positions()
    with sessions() as session:
        save_pending(
            session,
            PendingToolCallRow(
                request_id=request_id,
                game_id=context.game_id,
                tool_use={"id": tool_use_id, "input": tool_input},
                positions=[p.model_dump() for p in positions],
                extra_results=extra,
                tool_calls_used=tool_calls_used,
            ),
        )
    return EngineRequest(request_id=request_id, positions=positions)


async def _finish(
    client: CoachClient,
    settings: Settings,
    sessions: sessionmaker[Session],
    context: _Context,
    reply: CoachReply,
) -> FinalAnswer:
    """Validate the text answer, regenerating once and then removing invalid moves."""
    with sessions() as session:
        from_tools = _moves_in_tool_results(tool_results(session, context.game_id))
        messages = load_messages(session, context.game_id)
    allowed = set(context.allowed) | from_tools
    invalid = find_invalid(reply.text, allowed)
    if invalid:
        note = REGENERATE_NOTE.format(moves=", ".join(invalid))
        retry: list[MessageParam] = [
            *messages,
            cast(MessageParam, {"role": "assistant", "content": _dump(reply.content)}),
            {"role": "user", "content": note},
        ]
        request = replace(
            _request(settings, sessions, context, 0),
            messages=retry,
            tool_choice={"type": "none"},
        )
        reply = await _call(client, request, sessions, context.game_id)
        invalid = find_invalid(reply.text, allowed)
    text = reply.text
    if invalid:
        text = strip_moves(text, invalid)
        logger.warning(
            "coach moves removed: game=%s endpoint=chat moves=%s", context.game_id, invalid
        )
    with sessions() as session:
        save_turn(session, context.game_id, "assistant", [_text(text)])
    return FinalAnswer(text=text, invalid_moves_removed=invalid)


def _load_context(session: Session, settings: Settings, game_id: str) -> _Context:
    game = session.get(Game, game_id)
    summary = load_summary(session, game_id)
    if game is None or summary is None:
        raise LookupError(f"game {game_id} has no summary yet")
    parsed = parse_pgn(
        game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
    )
    data = {
        "pgn": movetext(parsed.positions),
        "game_summary": summary.model_dump(mode="json", exclude={"eval_curve"}),
    }
    synopsis = load_synopsis(session, game_id)
    block = f"{CONTEXT_INTRO}\n\n{json.dumps(data, separators=(',', ':'))}"
    if synopsis is not None:
        block += f"\n\nThe synopsis you already wrote for the player:\n\n{synopsis[0]}"
    return _Context(game_id, parsed, summary, block, frozenset(allowed_moves(data)))


def _cancel_pending(session: Session, game_id: str) -> None:
    """A new message abandons any analysis still waiting: answer it so the history stays valid."""
    pending = pending_for_game(session, game_id)
    if pending is None:
        return
    blocks = [_tool_result(pending.tool_use["id"], CANCELLED, error=True), *pending.extra_results]
    delete_pending(session, pending)
    save_turn(session, game_id, "user", blocks)


def _moves_in_tool_results(contents: Sequence[str]) -> set[str]:
    found: set[str] = set()
    for content in contents:
        found |= allowed_moves(content)  # error messages like "Nxe5 is not a legal move ..."
        with contextlib.suppress(json.JSONDecodeError):  # not every result is JSON
            found |= allowed_moves(json.loads(content))
    return found


async def _call(
    client: CoachClient, request: CoachRequest, sessions: sessionmaker[Session], game_id: str
) -> CoachReply:
    reply = await client.complete(request)
    with sessions() as session:
        record_usage(session, game_id, "chat", reply.model, reply.usage)
    return reply


def _text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _tool_result(tool_use_id: str, content: str, *, error: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if error:
        block["is_error"] = True
    return block


def _dump(content: Sequence[ContentBlock]) -> list[dict[str, Any]]:
    """Content blocks as JSON, unchanged (thinking signatures included) so they can be replayed."""
    return [block.model_dump(mode="json", exclude_none=True) for block in content]
