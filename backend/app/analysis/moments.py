"""Critical moments (SPEC_V2 §8): choosing them, grading the player's attempts, and hints.

All pure: no engine calls (the browser's searches come in as EngineResults), no I/O."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

import chess
from pydantic import BaseModel

from app.analysis.classify import Classification, classify, is_missed_mate
from app.analysis.detectors import PER_MOVE
from app.analysis.detectors.types import GameContext, MoveContext, ThemeFact
from app.analysis.engine import EngineResult
from app.analysis.evals import (
    Color,
    Evaluation,
    for_color,
    format_eval,
    terminal_evaluation,
    winning_chances,
)
from app.analysis.material import line_to_san
from app.analysis.moves import label
from app.analysis.phase import game_phase
from app.analysis.summary_models import Moment
from app.config import MomentSettings, Settings, Thresholds

_ERRORS = frozenset({"mistake", "blunder", "missed_mate"})


def select_moments(
    context: GameContext, facts: Sequence[ThemeFact], settings: MomentSettings
) -> list[Moment]:
    """SPEC_V2 §8.1: every mistake, blunder and missed mate; topped up with the biggest
    inaccuracies to `min_moments`; capped at `max_moments` keeping the biggest drops; in game
    order."""
    user_moves = context.user_moves()
    chosen = [m for m in user_moves if label(m) in _ERRORS]
    if len(chosen) < settings.min_moments:
        inaccuracies = sorted(
            (m for m in user_moves if label(m) == "inaccuracy"), key=lambda m: (-m.drop, m.ply)
        )
        chosen += inaccuracies[: settings.min_moments - len(chosen)]
    if len(chosen) > settings.max_moments:
        chosen = sorted(chosen, key=lambda m: (-m.drop, m.ply))[: settings.max_moments]
    ordered = sorted(chosen, key=lambda m: m.ply)
    return [_moment(index, move, facts, settings) for index, move in enumerate(ordered, start=1)]


def _moment(
    index: int, move: MoveContext, facts: Sequence[ThemeFact], settings: MomentSettings
) -> Moment:
    move_label = label(move)
    assert move_label is not None  # only labelled moves are chosen
    return Moment(
        index=index,
        ply=move.ply,
        move_number=move.move_number,
        side=move.color,
        san=move.san,
        uci=move.move.uci(),
        label=move_label,
        drop=round(move.drop, 4),
        eval_before=format_eval(move.eval_before),
        eval_after=format_eval(move.eval_after),
        themes=sorted({f.theme for f in facts if f.ply == move.ply}),
        refutation_san=line_to_san(
            move.board_after, move.best_line_after[: settings.refutation_plies]
        ),
        fen_before=move.board_before.fen(),
    )


# --- Grading an attempt (SPEC_V2 §8.3) ---

Grade = Literal["best", "good", "inaccuracy", "mistake", "blunder"]
SOLVED: frozenset[Grade] = frozenset({"best", "good"})


@dataclass(frozen=True)
class GradedMove:
    grade: Grade
    drop: float  # winning chances lost against the engine's best, for the side to move
    eval_after: Evaluation


def grade(
    board: chess.Board,
    move: chess.Move,
    before: EngineResult,
    after: EngineResult | None,
    thresholds: Thresholds,
    settings: MomentSettings,
) -> GradedMove:
    """`before` is the deep search of `board`; `after` of the position after `move` (None when
    the move ends the game: mate or stalemate are scored from the board)."""
    mover: Color = "white" if board.turn == chess.WHITE else "black"
    played = board.copy(stack=False)
    played.push(move)
    eval_after = terminal_evaluation(played)
    if eval_after is None:
        if after is None:
            raise ValueError(
                "a move that doesn't end the game needs a search of the position after"
            )
        eval_after = after.evaluation()
    drop = for_color(winning_chances(before.evaluation()) - winning_chances(eval_after), mover)
    top = chess.Move.from_uci(before.lines[0].moves_uci[0])
    result: Grade
    if move == top or drop < settings.best_margin:
        result = "best"
    elif drop < thresholds.inaccuracy:
        result = "good"
    else:
        result = classify(drop, thresholds) or "inaccuracy"
    return GradedMove(grade=result, drop=round(drop, 4), eval_after=eval_after)


def good_first_moves(board: chess.Board, before: EngineResult, thresholds: Thresholds) -> list[str]:
    """The first move (SAN) of every engine line that would grade "good" or better: the moves the
    coach must not name before the moment is solved or revealed (SPEC_V2 §8.4)."""
    mover: Color = "white" if board.turn == chess.WHITE else "black"
    best = winning_chances(before.evaluation())
    moves = []
    for line in before.lines:
        drop = for_color(best - winning_chances(line.evaluation()), mover)
        if drop < thresholds.inaccuracy:
            moves.append(board.san(chess.Move.from_uci(line.moves_uci[0])))
    return moves


def candidate_facts(
    board: chess.Board,
    move: chess.Move,
    ply: int,
    before: EngineResult,
    after: EngineResult | None,
    graded: GradedMove,
    settings: Settings,
) -> list[ThemeFact]:
    """The v1 detectors run on the player's attempt as if it had been played (SPEC_V2 §8.3)."""
    mover: Color = "white" if board.turn == chess.WHITE else "black"
    played = board.copy(stack=False)
    played.push(move)
    classification = None if graded.grade in SOLVED else cast(Classification, graded.grade)
    context = MoveContext(
        ply=ply,
        move_number=(ply + 1) // 2,
        color=mover,
        move=move,
        san=board.san(move),
        board_before=board.copy(stack=False),
        board_after=played,
        classification=classification,
        missed_mate=is_missed_mate(
            before.evaluation(), graded.eval_after, mover, settings.thresholds
        ),
        drop=graded.drop,
        eval_before=before.evaluation(),
        eval_after=graded.eval_after,
        best_line_before=_line(before),
        best_line_after=_line(after),
        phase=game_phase(board, ply, settings.detectors),
        clock_s=None,
        settings=settings.detectors,
    )
    if not context.flagged:
        return []
    return [fact for detect in PER_MOVE for fact in detect(context)]


def _line(result: EngineResult | None) -> tuple[chess.Move, ...]:
    if result is None:
        return ()
    return tuple(chess.Move.from_uci(uci) for uci in result.lines[0].moves_uci)


# --- Hints (SPEC_V2 §8.4) ---

HintValue = str | bool | list[str] | None


class Hint(BaseModel):
    level: int
    kind: Literal["candidate_problem", "best_move_shape"]
    text_facts: dict[str, HintValue]


# What a hint may say about the player's own move, per detector. Detectors that describe the
# engine's best move (missed_tactic, missed_capture_or_check, passive_king) are never used.
_HINT_FIELDS: dict[str, tuple[str, ...]] = {
    "hung_piece": ("piece", "square", "lost_to"),
    "allowed_tactic": ("subtype", "reply_move", "allows_mate"),
    "king_safety": ("pawn_moved", "opened_files"),
    "pawn_structure": ("weakness", "files"),
    "endgame_technique": ("subtype", "squares"),
}
_SAFE_ENDGAME = frozenset({"threw_win", "allowed_passer"})


def build_hints(
    facts: Sequence[ThemeFact],
    refutation_san: Sequence[str],
    board: chess.Board,
    best: chess.Move,
) -> list[Hint]:
    """Level 1: what's wrong with the player's move, from whitelisted detector fields (or the
    opponent's best reply when no detector fired). Level 2: the best move's shape (piece type,
    capture, check), never the move or its square."""
    problem: dict[str, HintValue] = {"theme": None}
    for fact in facts:
        fields = _HINT_FIELDS.get(fact.theme)
        if fields is None:
            continue
        if fact.theme == "endgame_technique" and fact.details.get("subtype") not in _SAFE_ENDGAME:
            continue
        problem = {"theme": fact.theme, **{f: _hint_value(fact.details.get(f)) for f in fields}}
        break
    if problem["theme"] is None:
        problem["opponent_best_reply"] = refutation_san[0] if refutation_san else None
    piece = board.piece_type_at(best.from_square)
    assert piece is not None
    shape: dict[str, HintValue] = {
        "piece_type": chess.piece_name(piece),
        "is_capture": board.is_capture(best),
        "is_check": board.gives_check(best),
    }
    return [
        Hint(level=1, kind="candidate_problem", text_facts=problem),
        Hint(level=2, kind="best_move_shape", text_facts=shape),
    ]


def _hint_value(value: object) -> HintValue:
    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, list):
        return [str(item) for item in value]
    return str(value)
