"""Critical moments taught Socratically (SPEC_V2 §8): start, attempt, reveal, a question, and the
wrap-up. Each step is prepared synchronously (checks, grading, saved progress) and then answered by
the coach in one call, single-turn, with a context stripped of everything that could give the
answer away (PLAN_V2 §6 Q2): withhold, don't instruct.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal, cast

import chess
from anthropic.types import MessageParam
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.engine import EngineResult, EngineResultError, Tier, check_for_position
from app.analysis.evals import format_eval, terminal_evaluation
from app.analysis.moments import (
    SOLVED,
    Grade,
    Hint,
    build_hints,
    candidate_facts,
    good_first_moves,
    grade,
)
from app.analysis.paths import ResolvedPath, resolve_path
from app.analysis.pgn import parse_pgn
from app.analysis.summary_models import GameSummary, Moment
from app.coach.annotations import (
    BoardFacts,
    engine_grades,
    plan_moves,
    san_to_keys,
)
from app.coach.client import CoachClient, CoachRequest, system_blocks
from app.coach.lines import moment_lines
from app.coach.markup import MessageTokens, Processed, ResolvedLine, Rules, note, process
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
from app.coach.validate import allowed_moves, normalize
from app.config import EngineTier, Settings
from app.db.annotations import log_dropped
from app.db.coach import record_usage
from app.db.engine_results import load_position_result, load_summary, save_position_result
from app.db.line_links import save_line_links
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
    "Your answer named or pointed out a move the player is supposed to find for themselves. "
    "Rewrite the complete answer without naming any move for the player to play, saying where a "
    "piece should go, or marking those squares on the board. Use only the facts and the hints "
    "listed in the data."
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
    facts: BoardFacts  # what board tags may show (SPEC_V3 §6.2), leak check included
    # The line links that resolve (SPEC_V3 §9.4), and those that would reveal the answer.
    lines: Mapping[str, ResolvedLine] = field(default_factory=dict)
    withheld: frozenset[str] = frozenset()
    meta: dict[str, str] | None = None


@dataclass(frozen=True)
class MomentAnswer:
    text: str
    invalid_moves_removed: list[str]
    meta: dict[str, str] | None = None
    leaked: bool = False
    tokens: MessageTokens = field(default_factory=MessageTokens)


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
        return _stored(intro)
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
        return _stored(stored)
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


def _stored(message: dict[str, Any]) -> MomentAnswer:
    tokens = MessageTokens.model_validate(message)  # absent keys: no tokens
    return MomentAnswer(text=str(message["text"]), invalid_moves_removed=[], tokens=tokens)


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
    rules = _rules(call, settings)
    text = await _complete(client, request, sessions, call)
    done = process(text, rules)
    if done.problems.any:
        if done.problems.leaked:  # logged even though the retry replaces this answer
            _log_leaks(sessions, call, done)
        retry: list[MessageParam] = [
            *messages,
            {"role": "assistant", "content": text},
            {"role": "user", "content": note(done.problems)},
        ]
        text = await _complete(client, replace(request, messages=retry), sessions, call)
        done = process(text, rules)
    leaked = done.problems.leaked
    if leaked:
        logger.warning("moment_leak: game=%s moment=%s", call.game_id, call.index)
    if done.removed:
        logger.warning(
            "coach moves removed: game=%s endpoint=moment moves=%s", call.game_id, done.removed
        )
    with sessions() as session:
        log_dropped(
            session,
            user_id=call.user_id,
            game_id=call.game_id,
            task=call.task,
            dropped=done.dropped,
            moment_index=call.index,
        )
        save_line_links(
            session, call.user_id, call.game_id, f"moment:{call.index}", done.line_links
        )
        row = progress_for(session, call.user_id, call.game_id, call.index)
        message = {"role": "coach", "text": done.text, "kind": call.kind}
        row.messages = [*row.messages, {**message, **done.tokens.model_dump(mode="json")}]
        row.leaks += 1 if leaked else 0
        session.commit()
    return MomentAnswer(
        text=done.text,
        invalid_moves_removed=done.removed,
        meta=call.meta,
        leaked=leaked,
        tokens=done.tokens,
    )


def _rules(call: MomentCall, settings: Settings) -> Rules:
    return Rules(
        allowed=call.allowed,
        limits=settings.coach,
        banned=frozenset(normalize(move) for move in call.banned),
        move_number=call.move_number,
        white_to_move=call.white_to_move,
        facts=call.facts,
        lines=call.lines,
        withheld=call.withheld,
    )


async def _complete(
    client: CoachClient, request: CoachRequest, sessions: sessionmaker[Session], call: MomentCall
) -> str:
    reply = await client.complete(request)
    with sessions() as session:
        record_usage(session, call.game_id, call.task, reply.model, reply.usage)
    return reply.text


def _log_leaks(sessions: sessionmaker[Session], call: MomentCall, drawn: Processed) -> None:
    logger.warning("moment_leak: game=%s moment=%s (regenerating)", call.game_id, call.index)
    with sessions() as session:
        log_dropped(
            session,
            user_id=call.user_id,
            game_id=call.game_id,
            task=call.task,
            dropped=[d for d in drawn.dropped if d.reason == "moment_leak"],
            moment_index=call.index,
        )
        session.commit()


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
        player = _scrub_player(player, banned)
    payload = CoachPayload(
        task=task,
        user_prompt=user_prompt,
        player=player,
        position=PositionPayload.model_validate(data.position.model_dump(exclude={"path_uci"})),
        engine_lines=engine_lines,
        moment=payload_moment,
    )
    context_block, context_data = _context(data)
    links, withheld = moment_lines(
        data.position.path_uci,
        moment.fen_before,
        moment.uci,
        payload_moment,
        settings.coach.line_link_max_plies,
    )
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
        facts=_board_facts(data, row, before if row.revealed else None, banned, settings),
        lines=links,
        withheld=withheld,
        meta=meta,
    )


def _board_facts(
    data: _Data,
    row: MomentProgressRow,
    before: EngineResult | None,
    banned: list[str],
    settings: Settings,
) -> BoardFacts:
    """What a moment answer may draw: the game's move and the player's tries (with their
    grades) and, once revealed, the engine lines. Before that, any arrow or highlight touching
    a move the player must find is a leak (SPEC_V3 §6.2; PLAN_V3 adjustment 3)."""
    moment = data.moment
    game_key = moment.uci[:4]
    label = moment.label
    game_grade: Grade = "mistake" if label == "missed_mate" else label
    graded: dict[str, Grade | None] = {}
    if before is not None:
        graded |= engine_grades(
            data.board, before, settings.thresholds, settings.moments.best_margin
        )
    graded[game_key] = game_grade
    tried = {a["uci"][:4]: cast(Grade, a["grade"]) for a in row.attempts}
    graded |= tried
    return BoardFacts(
        fen=moment.fen_before,
        graded=graded,
        mistake=game_key if game_grade != "inaccuracy" else None,
        plan_moves=plan_moves(before),
        banned=san_to_keys(moment.fen_before, banned),
        known=frozenset({game_key, *tried}),
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


def _scrub_player(player: PlayerPayload, banned: list[str]) -> PlayerPayload:
    """A tendency's example from another game can share its SAN with a move the player is meant
    to find here: leave that example's move out, so quoting it can't look like a leak."""
    targets = {normalize(m) for m in banned}
    tendencies = [
        t.model_copy(
            update={
                "recent_example": t.recent_example.model_copy(
                    update={"move_number": None, "move_san": None}
                )
            }
        )
        if t.recent_example.move_san and normalize(t.recent_example.move_san) in targets
        else t
        for t in player.tendencies
    ]
    return player.model_copy(update={"tendencies": tendencies})


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
