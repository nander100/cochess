"""Critical moments taught Socratically (SPEC_V2 §8): start, attempt, reveal, a question, and the
wrap-up. Each step is prepared synchronously (checks, grading, saved progress) and then answered by
the coach in one call, single-turn, with a context stripped of everything that could give the
answer away (PLAN_V2 §6 Q2): withhold, don't instruct.
"""

import json
import logging
from dataclasses import dataclass, field, replace
from typing import Any, Literal, cast

import chess
from anthropic.types import MessageParam
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.engine import EngineResult, EngineResultError, Tier, check_for_position
from app.analysis.evals import format_eval, terminal_evaluation
from app.analysis.moments import (
    SOLVED,
    Hint,
    build_hints,
    candidate_facts,
    good_first_moves,
    grade,
)
from app.analysis.paths import ResolvedPath, resolve_path
from app.analysis.pgn import parse_pgn
from app.analysis.summary_models import GameSummary, Moment
from app.coach.client import CoachClient, CoachRequest, system_blocks
from app.coach.payload import (
    CoachPayload,
    MomentAttempt,
    MomentBest,
    MomentCandidate,
    MomentGameMove,
    MomentPayload,
    MomentResult,
    PlayerPayload,
    PositionPayload,
    Task,
    annotated_movetext,
    render,
)
from app.coach.tools import line_summaries
from app.coach.validate import allowed_moves, find_invalid, find_leaks, normalize, strip_moves
from app.config import EngineTier, Settings
from app.db.coach import record_usage
from app.db.engine_results import load_position_result, load_summary, save_position_result
from app.db.models import Game, MomentProgressRow
from app.db.moments import load_progress, progress_for

logger = logging.getLogger(__name__)

MOMENT_INSTRUCTION = (
    "The critical-moment exercise, as JSON. Respond as described in your instructions for its "
    "state."
)
CONTEXT_INTRO = (
    "Context for this exercise: the player's game up to the critical moment, and the list of "
    "moments, as JSON."
)
# Deliberately names no move: telling the coach the answer would defeat the withholding.
LEAK_NOTE = (
    "Your answer named a move the player is supposed to find for themselves. Rewrite the complete "
    "answer without naming any move for the player to play or saying where a piece should go. "
    "Use only the facts and the hints listed in the data."
)
INVALID_NOTE = (
    "Your answer mentioned moves that are not in the data: {moves}. Only write moves that appear "
    "in the data, and describe pieces and squares in words."
)

DEEP: tuple[Tier, ...] = ("deep",)

Kind = Literal["intro", "feedback", "reveal", "answer", "wrap_up"]


class MomentError(Exception):
    """The request can't be done; `status` is the HTTP status, `message` is safe to show."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class MomentCall:
    """A prepared coach call for a moment step."""

    user_id: str
    game_id: str
    index: int
    task: Task
    kind: Kind
    payload: CoachPayload
    context_block: str
    allowed: frozenset[str]
    banned: tuple[str, ...]  # empty once the moment is revealed
    move_number: int
    white_to_move: bool
    meta: dict[str, str] | None = None


@dataclass(frozen=True)
class MomentAnswer:
    text: str
    invalid_moves_removed: list[str]
    meta: dict[str, str] | None = None
    leaked: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Data:
    summary: GameSummary
    moment: Moment
    of: int
    board: chess.Board
    position: ResolvedPath


# --- Preparing each step ---


def prepare_start(
    session: Session, settings: Settings, game: Game, player: PlayerPayload, index: int
) -> MomentCall | MomentAnswer:
    """Begin a moment, or return to it: a stored intro is shown again without a new coach call."""
    data = _load(session, settings, game, index)
    row = progress_for(session, cast(str, game.user_id), game.id, index)
    intro = next((m for m in row.messages if m.get("kind") == "intro"), None)
    session.commit()
    if intro is not None:
        return MomentAnswer(text=str(intro["text"]), invalid_moves_removed=[])
    return _call(session, settings, game, data, row, "moment_intro", "intro", player)


def prepare_attempt(
    session: Session,
    settings: Settings,
    game: Game,
    player: PlayerPayload,
    index: int,
    candidate_uci: str,
    reasoning: str | None,
    before_result: EngineResult | None,
    after_result: EngineResult | None,
) -> MomentCall:
    data = _load(session, settings, game, index)
    row = progress_for(session, cast(str, game.user_id), game.id, index)
    if row.state in ("solved", "revealed"):
        raise MomentError(409, "This moment is finished. Go on to the next one.")
    board = data.board
    try:
        move = chess.Move.from_uci(candidate_uci)
    except chess.InvalidMoveError as error:
        raise MomentError(422, "That isn't a valid move.") from error
    if move not in board.legal_moves:
        raise MomentError(422, "That move isn't legal in this position.")

    before = _before(session, settings, game, data, before_result)
    played = board.copy(stack=False)
    played.push(move)
    after = None
    if terminal_evaluation(played) is None:
        if after_result is None:
            raise MomentError(409, "Analyze your move with the engine first.")
        after = _checked(after_result, played.fen(), settings)
    graded = grade(board, move, before, after, settings.thresholds, settings.moments)
    facts = candidate_facts(board, move, data.moment.ply, before, after, graded, settings)
    plies = settings.moments.refutation_plies
    refutation = line_summaries(played.fen(), after)[0].moves_san[:plies] if after else []
    same_as_game = move.uci() == data.moment.uci
    best_move = chess.Move.from_uci(before.lines[0].moves_uci[0])
    hints = build_hints(facts, refutation, board, best_move)

    attempt: dict[str, Any] = {
        "uci": move.uci(),
        "san": board.san(move),
        "grade": graded.grade,
        "reasoning": (reasoning or "").strip() or None,
        "eval_after": format_eval(graded.eval_after),
        "themes": sorted({f.theme for f in facts}),
        "refutation_san": refutation,
        "same_as_game": same_as_game,
        "hints": [h.model_dump() for h in hints],
    }
    row.attempts = [*row.attempts, attempt]
    failures = sum(a["grade"] not in SOLVED for a in row.attempts)
    if graded.grade in SOLVED:
        row.state = "solved"
    elif failures >= settings.moments.max_attempts:
        row.state = "revealed"
    else:
        row.state = "attempt"
    row.revealed = row.state in ("solved", "revealed")
    said = attempt["san"] + (f": {attempt['reasoning']}" if attempt["reasoning"] else "")
    row.messages = [*row.messages, {"role": "player", "text": said, "kind": "attempt"}]
    candidate = MomentCandidate(
        san=_numbered(data.moment.move_number, data.moment.side == "white", attempt["san"]),
        grade=graded.grade,
        eval_after=attempt["eval_after"],
        themes=attempt["themes"],
        refutation_san=refutation,
    )
    # One hint after a failed try (lowest level first); none after the game's own move again.
    allowed_hints = hints[:1] if row.state == "attempt" and not same_as_game else []
    return _call(
        session,
        settings,
        game,
        data,
        row,
        "moment_feedback",
        "feedback",
        player,
        candidate=candidate,
        hints=allowed_hints,
        same_as_game=same_as_game,
        before=before,
        meta={"grade": graded.grade, "state": row.state},
    )


def prepare_reveal(
    session: Session,
    settings: Settings,
    game: Game,
    player: PlayerPayload,
    index: int,
    before_result: EngineResult | None,
) -> MomentCall:
    """ "Show me" (SPEC_V2 §8.2): reveal the answer whatever the attempts so far."""
    data = _load(session, settings, game, index)
    row = progress_for(session, cast(str, game.user_id), game.id, index)
    if row.state in ("solved", "revealed"):
        raise MomentError(409, "This moment is already finished.")
    before = _before(session, settings, game, data, before_result)
    row.state, row.revealed = "revealed", True
    row.messages = [*row.messages, {"role": "player", "text": "Show me.", "kind": "reveal"}]
    return _call(
        session,
        settings,
        game,
        data,
        row,
        "moment_feedback",
        "reveal",
        player,
        before=before,
        meta={"state": "revealed"},
    )


def prepare_question(
    session: Session, settings: Settings, game: Game, player: PlayerPayload, index: int, text: str
) -> MomentCall:
    """A question during the exercise: answered under the same withholding (PLAN_V2 §6 Q3)."""
    data = _load(session, settings, game, index)
    row = progress_for(session, cast(str, game.user_id), game.id, index)
    before = None
    hints: list[Hint] = []
    if row.revealed:
        before = load_position_result(session, game.id, data.moment.fen_before, tiers=DEEP)
    else:
        failed = [a for a in row.attempts if a["grade"] not in SOLVED]
        if failed:  # after a failed try, the player may get both hint levels
            hints = [Hint.model_validate(h) for h in failed[-1]["hints"]]
    row.messages = [*row.messages, {"role": "player", "text": text, "kind": "question"}]
    return _call(
        session,
        settings,
        game,
        data,
        row,
        "moment_feedback",
        "answer",
        player,
        hints=hints,
        before=before,
        user_prompt=text,
    )


def prepare_wrap_up(
    session: Session, settings: Settings, game: Game, player: PlayerPayload
) -> MomentCall | MomentAnswer:
    """After the last moment (SPEC_V2 §8.2): a short wrap-up, stored with the last moment."""
    summary = _summary(session, game)
    if not summary.moments:
        raise MomentError(409, "This game has no critical moments.")
    progress = load_progress(session, game.id)
    results = []
    for moment in summary.moments:
        done = progress.get(moment.index)
        if done is None or done.state not in ("solved", "revealed"):
            raise MomentError(409, "Finish every moment first.")
        results.append(
            MomentResult(
                index=moment.index,
                game_move=_numbered(moment.move_number, moment.side == "white", moment.san),
                outcome=cast(Literal["solved", "revealed"], done.state),
                attempts=len(done.attempts),
            )
        )
    last = summary.moments[-1]
    row = progress[last.index]
    stored = next((m for m in row.messages if m.get("kind") == "wrap_up"), None)
    if stored is not None:
        return MomentAnswer(text=str(stored["text"]), invalid_moves_removed=[])
    data = _load(session, settings, game, last.index)
    before = load_position_result(session, game.id, last.fen_before, tiers=DEEP)
    return _call(
        session,
        settings,
        game,
        data,
        row,
        "moment_feedback",
        "wrap_up",
        player,
        before=before,
        wrap_up=results,
    )


# --- The coach call ---


async def answer(
    client: CoachClient, settings: Settings, sessions: sessionmaker[Session], call: MomentCall
) -> MomentAnswer:
    """One coach call, validated (SPEC_V2 §7.4) and leak-checked (§8.4): regenerate once, then
    remove what's still wrong; a remaining leak is logged as a moment_leak incident."""
    messages: list[MessageParam] = [
        {"role": "user", "content": render(call.payload, MOMENT_INSTRUCTION)}
    ]
    request = CoachRequest(
        model=settings.coach_model_chat,
        system=system_blocks(call.task, call.context_block),
        messages=messages,
        max_tokens=settings.coach.chat_max_tokens,
        effort=settings.coach.chat_effort,
    )
    text = await _complete(client, request, sessions, call)
    invalid, leaks = _problems(text, call)
    if invalid or leaks:
        notes = ([LEAK_NOTE] if leaks else []) + (
            [INVALID_NOTE.format(moves=", ".join(invalid))] if invalid else []
        )
        retry: list[MessageParam] = [
            *messages,
            {"role": "assistant", "content": text},
            {"role": "user", "content": " ".join(notes)},
        ]
        text = await _complete(client, replace(request, messages=retry), sessions, call)
        invalid, leaks = _problems(text, call)
    if leaks:
        text = strip_moves(text, leaks)
        logger.warning("moment_leak: game=%s moment=%s moves=%s", call.game_id, call.index, leaks)
    if invalid:
        text = strip_moves(text, invalid)
        logger.warning(
            "coach moves removed: game=%s endpoint=moment moves=%s", call.game_id, invalid
        )
    with sessions() as session:
        row = progress_for(session, call.user_id, call.game_id, call.index)
        row.messages = [*row.messages, {"role": "coach", "text": text, "kind": call.kind}]
        row.leaks += 1 if leaks else 0
        session.commit()
    return MomentAnswer(text=text, invalid_moves_removed=invalid, meta=call.meta, leaked=leaks)


async def _complete(
    client: CoachClient, request: CoachRequest, sessions: sessionmaker[Session], call: MomentCall
) -> str:
    reply = await client.complete(request)
    with sessions() as session:
        record_usage(session, call.game_id, call.task, reply.model, reply.usage)
    return reply.text


def _problems(text: str, call: MomentCall) -> tuple[list[str], list[str]]:
    leaks = find_leaks(text, call.banned, call.move_number, call.white_to_move)
    # A leaked move isn't in the data either; report it once, as a leak.
    invalid = [m for m in find_invalid(text, set(call.allowed)) if m not in leaks]
    return invalid, leaks


# --- Building the payload ---


def _call(
    session: Session,
    settings: Settings,
    game: Game,
    data: _Data,
    row: MomentProgressRow,
    task: Task,
    kind: Kind,
    player: PlayerPayload,
    *,
    candidate: MomentCandidate | None = None,
    hints: list[Hint] | None = None,
    same_as_game: bool = False,
    before: EngineResult | None = None,
    user_prompt: str | None = None,
    wrap_up: list[MomentResult] | None = None,
    meta: dict[str, str] | None = None,
) -> MomentCall:
    moment = data.moment
    best = engine_lines = None
    banned: list[str] = []
    if row.revealed and before is not None:
        lines = line_summaries(moment.fen_before, before)
        plies, count = settings.coach.coach_line_plies, settings.coach.coach_engine_lines
        trimmed = [line.model_copy(update={"moves_san": line.moves_san[:plies]}) for line in lines]
        best = MomentBest(
            san=lines[0].moves_san[0], eval=format_eval(before.evaluation()), lines=trimmed[:count]
        )
        engine_lines = trimmed[:count]
    elif not row.revealed:
        stored = before or load_position_result(
            session, game.id, moment.fen_before, tiers=("deep", "verify")
        )
        if stored is not None:
            # The player's own tries are theirs to discuss, even one the engine rates close.
            tried = {normalize(a["san"]) for a in row.attempts}
            banned = [
                m
                for m in good_first_moves(data.board, stored, settings.thresholds)
                if normalize(m) not in tried
            ]

    payload_moment = MomentPayload(
        index=moment.index,
        of=data.of,
        state=cast(Literal["intro", "attempt", "solved", "revealed"], row.state),
        game_move=MomentGameMove(
            san=_numbered(moment.move_number, moment.side == "white", moment.san),
            classification=moment.label,
            eval_before=moment.eval_before,
            eval_after=moment.eval_after,
            themes=list(moment.themes),
            refutation_san=list(moment.refutation_san),
        ),
        candidate=candidate,
        earlier_attempts=[
            MomentAttempt(san=a["san"], grade=a["grade"], reasoning=a["reasoning"])
            for a in row.attempts
        ],
        attempt_number=len(row.attempts),
        max_attempts=settings.moments.max_attempts,
        hints_allowed=list(hints or []),
        same_as_game=same_as_game,
        reveal=row.revealed,
        best=best,
        wrap_up=wrap_up is not None,
        results=list(wrap_up or []),
    )
    if banned:
        payload_moment = _scrub(payload_moment, banned)
    payload = CoachPayload(
        task=task,
        user_prompt=user_prompt,
        player=player,
        position=PositionPayload.model_validate(data.position.model_dump(exclude={"path_uci"})),
        engine_lines=engine_lines,
        moment=payload_moment,
    )
    context_block, context_data = _context(data)
    allowed = allowed_moves(context_data) | allowed_moves(payload.model_dump(mode="json"))
    session.commit()
    return MomentCall(
        user_id=cast(str, game.user_id),
        game_id=game.id,
        index=moment.index,
        task=task,
        kind=kind,
        payload=payload,
        context_block=context_block,
        allowed=frozenset(allowed),
        banned=tuple(banned),
        move_number=moment.move_number,
        white_to_move=moment.side == "white",
        meta=meta,
    )


def _scrub(moment: MomentPayload, banned: list[str]) -> MomentPayload:
    """Keep the payload free of the moves the player is meant to find (PLAN_V2 §6 Q2): a line is
    cut just before the first one (it can come up later, as another move of the line), and a hint
    that names one is dropped. The line up to there still shows what happens next."""
    targets = {normalize(m) for m in banned}

    def clean(moves: list[str]) -> list[str]:
        kept = []
        for move in moves:
            if normalize(move) in targets:
                break
            kept.append(move)
        return kept

    game_move = moment.game_move.model_copy(
        update={"refutation_san": clean(moment.game_move.refutation_san)}
    )
    candidate = moment.candidate
    if candidate is not None:
        candidate = candidate.model_copy(update={"refutation_san": clean(candidate.refutation_san)})
    hints = [h for h in moment.hints_allowed if not allowed_moves(h.model_dump()) & targets]
    return moment.model_copy(
        update={"game_move": game_move, "candidate": candidate, "hints_allowed": hints}
    )


def _context(data: _Data) -> tuple[str, dict[str, Any]]:
    """The game only up to the moment, and the moments' list: no synopsis, no chat, no key-moment
    lines or detector details, which name the moves the player is meant to find."""
    earlier = [m for m in data.summary.move_list if m.ply < data.moment.ply]
    movetext = annotated_movetext(data.summary.model_copy(update={"move_list": earlier}))
    context = {
        "game": data.summary.game.model_dump(mode="json"),
        "player_color": data.summary.user.color,
        "pgn_to_move": movetext,
        "moments": [
            {
                "index": m.index,
                "move": _numbered(m.move_number, m.side == "white", m.san),
                "classification": m.label,
            }
            for m in data.summary.moments
        ],
    }
    return f"{CONTEXT_INTRO}\n\n{json.dumps(context, separators=(',', ':'))}", context


# --- Loading ---


def _summary(session: Session, game: Game) -> GameSummary:
    summary = load_summary(session, game.id)
    if summary is None:
        raise MomentError(409, "Finish the engine analysis first.")
    return summary


def _load(session: Session, settings: Settings, game: Game, index: int) -> _Data:
    summary = _summary(session, game)
    moment = next((m for m in summary.moments if m.index == index), None)
    if moment is None:
        raise MomentError(404, "There's no such moment in this game.")
    parsed = parse_pgn(
        game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
    )
    path = [p.uci for p in parsed.positions[: moment.ply - 1]]
    position = resolve_path(parsed, path, settings.limits.max_plies)
    return _Data(summary, moment, len(summary.moments), chess.Board(moment.fen_before), position)


def _before(
    session: Session,
    settings: Settings,
    game: Game,
    data: _Data,
    provided: EngineResult | None,
) -> EngineResult:
    """The deep search of the moment's position: sent by the browser once, then stored."""
    if provided is not None:
        save_position_result(session, game.id, _checked(provided, data.moment.fen_before, settings))
    stored = load_position_result(session, game.id, data.moment.fen_before, tiers=DEEP)
    if stored is None:
        raise MomentError(409, "Analyze the position with the engine first.")
    return stored


def _checked(result: EngineResult, fen: str, settings: Settings) -> EngineResult:
    tiers: dict[Tier, EngineTier] = {"deep": settings.engine.deep}
    try:
        return check_for_position(result, fen=fen, tier_configs=tiers)
    except EngineResultError as error:
        raise MomentError(422, error.message) from error


def _numbered(move_number: int, white: bool, san: str) -> str:
    return f"{move_number}. {san}" if white else f"{move_number}...{san}"
