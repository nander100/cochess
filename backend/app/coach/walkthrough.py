"""Guided line walkthroughs (SPEC_V3 §7): one forced-tool coach call for a whole line of up to
10 plies, then validation: one step per ply, every move named is in the line or the data, and
each step's arrows and highlights pass §6.2 on the position after that step's move. A reply with
the wrong steps or moves outside the data is regenerated once.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import cast

import chess
from anthropic.types import MessageParam, ToolParam
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.engine import EngineResult
from app.analysis.evals import Evaluation, format_eval, terminal_evaluation, win_percent
from app.analysis.moments import Grade
from app.analysis.move_facts import StepFacts, step_facts
from app.analysis.paths import ResolvedPath
from app.coach.annotations import (
    Annotation,
    BoardFacts,
    Dropped,
    check_shapes,
    engine_grades,
    plan_moves,
)
from app.coach.client import CoachClient, CoachReply, CoachRequest, system_blocks
from app.coach.markup import MoveToken, Problems, Processed, Rules, note, process
from app.coach.payload import (
    CoachPayload,
    PlayerPayload,
    PositionPayload,
    WalkthroughPayload,
    render,
)
from app.coach.validate import allowed_moves, normalize
from app.config import Settings
from app.db.annotations import log_dropped
from app.db.coach import record_usage

logger = logging.getLogger(__name__)

TOOL_NAME = "line_walkthrough"
LINE_WALKTHROUGH: ToolParam = {
    "name": TOOL_NAME,
    "description": "Walk the player through the line, one step per move.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intro": {"type": "string"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "text": {"type": "string", "description": "≤ 50 words"},
                        "arrows": {
                            "type": "array",
                            "items": {"type": "string", "description": "fromto:color"},
                        },
                        "squares": {
                            "type": "array",
                            "items": {"type": "string", "description": "square:color"},
                        },
                    },
                    "required": ["index", "text"],
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["intro", "steps", "summary"],
    },
}
INSTRUCTION = "The line to walk through, as JSON. Call line_walkthrough as your instructions say."
RETRY_NOTE = (
    "That walkthrough can't be used: {problems}. Call line_walkthrough again with the complete "
    "walkthrough: exactly one step per move of the line, indexed 1 to {plies}, naming only moves "
    "from the line, the step facts, or the game so far, and describing pieces and squares in words."
)
FAILED = "The coach couldn't put this walkthrough together. Please try again."


class WalkthroughError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class WalkthroughStep(BaseModel):
    index: int
    uci: str
    san: str
    fen_after: str
    eval_after: str | None
    win_pct_after: float | None  # White's, 0..100, for the eval bar
    text: str
    annotation: Annotation | None = None
    moves: list[MoveToken] = []  # the text's move tags (SPEC_V3 §9.4)


class Walkthrough(BaseModel):
    start_path_uci: list[str]
    line_uci: list[str]
    start_fen: str
    intro: str
    steps: list[WalkthroughStep]
    summary: str
    invalid_moves_removed: list[str] = []
    intro_moves: list[MoveToken] = []
    summary_moves: list[MoveToken] = []


class _ToolStep(BaseModel):
    index: int
    text: str
    arrows: list[str] = Field(default_factory=list)
    squares: list[str] = Field(default_factory=list)


class _ToolOutput(BaseModel):
    intro: str
    steps: list[_ToolStep]
    summary: str


@dataclass(frozen=True)
class WalkthroughCall:
    user_id: str
    game_id: str
    start: ResolvedPath
    line_uci: tuple[str, ...]
    line_san: tuple[str, ...]
    fens_after: tuple[str, ...]
    evals: tuple[Evaluation | None, ...]  # the start, then after each move
    results: Mapping[str, EngineResult]  # by FEN: the per-step scans
    payload: CoachPayload
    allowed: frozenset[str]
    # Each move of the game so far and of the line: the (number, white) it really has.
    numbering: Mapping[str, frozenset[tuple[int, bool]]]


def build_call(
    user_id: str,
    game_id: str,
    start: ResolvedPath,
    line_uci: Sequence[str],
    results: Mapping[str, EngineResult],
    player: PlayerPayload,
    swing_cp: int,
) -> WalkthroughCall:
    """The payload for a checked line: `results` hold a search of every position along it that
    isn't checkmate or stalemate (those are scored from the board)."""
    board = chess.Board(start.fen)
    fens = [start.fen]
    sans = []
    for uci in line_uci:
        move = chess.Move.from_uci(uci)
        sans.append(board.san(move))
        board.push(move)
        fens.append(board.fen())
    evals = tuple(_evaluation(fen, results) for fen in fens)
    facts = step_facts(start.fen, line_uci, evals, swing_cp)
    payload = CoachPayload(
        task="walkthrough",
        player=player,
        position=PositionPayload.model_validate(start.model_dump(exclude={"path_uci"})),
        walkthrough=WalkthroughPayload(line_san=sans, steps=facts),
    )
    return WalkthroughCall(
        user_id=user_id,
        game_id=game_id,
        start=start,
        line_uci=tuple(line_uci),
        line_san=tuple(sans),
        fens_after=tuple(fens[1:]),
        evals=evals,
        results=results,
        payload=payload,
        allowed=frozenset(allowed_moves(payload.model_dump(mode="json"))),
        numbering=_numbering(start, facts),
    )


def _numbering(
    start: ResolvedPath, facts: Sequence[StepFacts]
) -> dict[str, frozenset[tuple[int, bool]]]:
    pairs: dict[str, set[tuple[int, bool]]] = {}
    for ply, san in enumerate(start.path_san, start=1):
        pairs.setdefault(normalize(san), set()).add(((ply + 1) // 2, ply % 2 == 1))
    for fact in facts:
        pairs.setdefault(normalize(fact.san), set()).add((fact.move_number, fact.side == "white"))
    return {san: frozenset(numbers) for san, numbers in pairs.items()}


def _evaluation(fen: str, results: Mapping[str, EngineResult]) -> Evaluation | None:
    terminal = terminal_evaluation(chess.Board(fen))
    if terminal is not None:
        return terminal
    result = results.get(fen)
    return result.evaluation() if result is not None else None


async def generate(
    client: CoachClient, settings: Settings, sessions: sessionmaker[Session], call: WalkthroughCall
) -> Walkthrough:
    messages: list[MessageParam] = [{"role": "user", "content": render(call.payload, INSTRUCTION)}]
    request = CoachRequest(
        model=settings.coach_model_chat,
        system=system_blocks("walkthrough"),
        messages=messages,
        max_tokens=settings.coach.walkthrough_max_tokens,
        effort=settings.coach.walkthrough_effort,
        tools=[LINE_WALKTHROUGH],
        tool_choice={"type": "tool", "name": TOOL_NAME},
    )
    reply = await _complete(client, request, sessions, call.game_id)
    output, problems = _check(reply, call, settings)
    if problems:
        retry = [*messages, *_retry_turns(reply, problems, len(call.line_uci))]
        reply = await _complete(client, replace(request, messages=retry), sessions, call.game_id)
        output, problems = _check(reply, call, settings)
    if output is None:
        logger.warning("walkthrough failed: game=%s problems=%s", call.game_id, problems)
        raise WalkthroughError(FAILED)
    return _finish(output, call, settings, sessions)


def _check(
    reply: CoachReply, call: WalkthroughCall, settings: Settings
) -> tuple[_ToolOutput | None, list[str]]:
    """The tool output if its structure is usable, and what's wrong with it. Moves outside the
    data still leave a usable output: they're removed if the retry doesn't fix them."""
    block = next((b for b in reply.content if b.type == "tool_use" and b.name == TOOL_NAME), None)
    if block is None:
        return None, ["no line_walkthrough call"]
    try:
        output = _ToolOutput.model_validate(block.input)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        cut = " (the reply was cut off)" if reply.stop_reason == "max_tokens" else ""
        return None, [f"the tool input doesn't match the schema at {where}: {first['msg']}{cut}"]
    plies = len(call.line_uci)
    if [s.index for s in output.steps] != list(range(1, plies + 1)):
        return None, [f"the steps must be indexed 1 to {plies}, one per move"]
    merged = _merged([done.problems for done in _process(output, call, settings)])
    return output, [note(merged)] if merged.any else []


def _process(output: _ToolOutput, call: WalkthroughCall, settings: Settings) -> list[Processed]:
    """The intro, each step's text and the summary, through the markup checks (SPEC_V3 §9.4):
    move tags only, from the data, with the right numbers, one at a time."""
    rules = Rules(
        allowed=call.allowed, limits=settings.coach, numbering=call.numbering,
        words_only_evals=call.payload.player.detail_level == "plain", puzzles=settings.puzzles,
    )  # fmt: skip
    texts = [output.intro, *(step.text for step in output.steps), output.summary]
    return [process(text, rules) for text in texts]


def _merged(all_problems: list[Problems]) -> Problems:
    merged = Problems()
    for problems in all_problems:
        for name in ("invalid", "leaks", "bare", "misnumbered", "line_leaks"):
            bucket = getattr(merged, name)
            bucket += [m for m in getattr(problems, name) if m not in bucket]
        merged.runs += problems.runs
    return merged


def _retry_turns(reply: CoachReply, problems: list[str], plies: int) -> list[MessageParam]:
    note = RETRY_NOTE.format(problems="; ".join(problems), plies=plies)
    content = [b.model_dump(mode="json", exclude_none=True) for b in reply.content]
    assistant = cast(MessageParam, {"role": "assistant", "content": content})
    tool_use = next((b for b in reply.content if b.type == "tool_use"), None)
    if tool_use is None:
        return [assistant, {"role": "user", "content": note}]
    result = {"type": "tool_result", "tool_use_id": tool_use.id, "content": note, "is_error": True}
    return [assistant, cast(MessageParam, {"role": "user", "content": [result]})]


def _finish(
    output: _ToolOutput, call: WalkthroughCall, settings: Settings, sessions: sessionmaker[Session]
) -> Walkthrough:
    # Moves outside the data, or written with a number they don't have, are removed.
    done = _process(output, call, settings)
    intro, texts, summary = done[0], done[1:-1], done[-1]
    invalid: list[str] = []
    for part in done:
        invalid += [m for m in part.removed if m not in invalid]
    if invalid:
        logger.warning(
            "coach moves removed: game=%s endpoint=walkthrough moves=%s", call.game_id, invalid
        )

    steps: list[WalkthroughStep] = []
    dropped: list[Dropped] = []
    for i, step in enumerate(output.steps):
        if len(step.text.split()) > settings.coach.walkthrough_step_max_words:
            logger.warning("walkthrough step too long: game=%s step=%d", call.game_id, step.index)
        annotation, rejected = check_shapes(
            step.arrows,
            step.squares,
            _facts_after(call, i, settings),
            settings.coach,
            label=f"step {step.index}",
        )
        dropped += rejected
        evaluation = call.evals[i + 1]
        steps.append(
            WalkthroughStep(
                index=step.index,
                uci=call.line_uci[i],
                san=call.line_san[i],
                fen_after=call.fens_after[i],
                eval_after=format_eval(evaluation) if evaluation is not None else None,
                win_pct_after=win_percent(evaluation) if evaluation is not None else None,
                text=texts[i].text,
                annotation=annotation,
                moves=texts[i].moves,
            )
        )
    with sessions() as session:
        log_dropped(
            session, user_id=call.user_id, game_id=call.game_id, task="walkthrough", dropped=dropped
        )
        session.commit()
    return Walkthrough(
        start_path_uci=call.start.path_uci,
        line_uci=list(call.line_uci),
        start_fen=call.start.fen,
        intro=intro.text,
        steps=steps,
        summary=summary.text,
        invalid_moves_removed=invalid,
        intro_moves=intro.moves,
        summary_moves=summary.moves,
    )


def _facts_after(call: WalkthroughCall, i: int, settings: Settings) -> BoardFacts:
    """What step i+1's shapes may show, on the position after its move: the engine's lines
    there (graded), the line's next move, threats, and plans from those lines."""
    fen = call.fens_after[i]
    result = call.results.get(fen)
    graded: dict[str, Grade | None] = {}
    if result is not None:
        board = chess.Board(fen)
        graded |= engine_grades(board, result, settings.thresholds, settings.moments.best_margin)
    if i + 1 < len(call.line_uci):
        graded.setdefault(call.line_uci[i + 1][:4], None)
    return BoardFacts(fen=fen, graded=graded, plan_moves=plan_moves(result))


async def _complete(
    client: CoachClient, request: CoachRequest, sessions: sessionmaker[Session], game_id: str
) -> CoachReply:
    reply = await client.complete(request)
    with sessions() as session:
        record_usage(session, game_id, "walkthrough", reply.model, reply.usage)
    return reply
