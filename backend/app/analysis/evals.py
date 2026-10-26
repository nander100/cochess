"""Evaluations and winning chances (SPEC §5.1, §6.1). Every eval here is from White's POV.

The browser converts the engine's side-to-move scores to White's POV in exactly one place
(frontend `engine/score.ts`, PLAN Q4); the backend never converts them again.
"""

import math
from typing import Literal, Self

import chess
from pydantic import BaseModel, ConfigDict, model_validator

# Lichess winning-chances model (scalachess `WinPercent`, multiplier from lila PR #11148).
WC_MULTIPLIER = -0.00368208
# Lichess clamps centipawns to ±1000 before converting (PLAN Q9).
CP_CEILING = 1000

Color = Literal["white", "black"]


class Evaluation(BaseModel):
    """A position's evaluation, White POV. Exactly one field is set."""

    model_config = ConfigDict(frozen=True)

    cp: int | None = None
    mate: int | None = None  # moves to mate; positive = White mates. Never 0.
    checkmated: Color | None = None  # the position is already checkmate; this side is mated

    @model_validator(mode="after")
    def exactly_one_form(self) -> Self:
        if sum(x is not None for x in (self.cp, self.mate, self.checkmated)) != 1:
            raise ValueError("exactly one of cp, mate, checkmated must be set")
        if self.mate == 0:
            raise ValueError("mate must be non-zero; use checkmated for a mated position")
        return self


def terminal_evaluation(board: chess.Board) -> Evaluation | None:
    """Evaluate positions the engine can't search (no legal moves). None if not terminal."""
    if board.is_checkmate():
        return Evaluation(checkmated="white" if board.turn == chess.WHITE else "black")
    if board.is_stalemate():
        return Evaluation(cp=0)
    return None


def winning_chances(evaluation: Evaluation) -> float:
    """White's winning chances in -1..1. Mate scores map to ±1 (SPEC §6.1, PLAN Q10)."""
    if evaluation.checkmated is not None:
        return 1.0 if evaluation.checkmated == "black" else -1.0
    if evaluation.mate is not None:
        return 1.0 if evaluation.mate > 0 else -1.0
    assert evaluation.cp is not None
    cp = max(-CP_CEILING, min(CP_CEILING, evaluation.cp))
    return 2 / (1 + math.exp(WC_MULTIPLIER * cp)) - 1


def win_percent(evaluation: Evaluation) -> float:
    """White's win% in 0..100."""
    return 50 + 50 * winning_chances(evaluation)


def for_color(white_value: float, color: Color) -> float:
    """Flip a White-POV winning-chances value to `color`'s POV."""
    return white_value if color == "white" else -white_value


def format_eval(evaluation: Evaluation) -> str:
    """Display format: +0.3, -2.0, 0.0, +M3, -M2. A delivered mate shows as +M0 / -M0."""
    if evaluation.checkmated is not None:
        return "+M0" if evaluation.checkmated == "black" else "-M0"
    if evaluation.mate is not None:
        return f"+M{evaluation.mate}" if evaluation.mate > 0 else f"-M{-evaluation.mate}"
    assert evaluation.cp is not None
    pawns = round(evaluation.cp / 100, 1)
    return "0.0" if pawns == 0 else f"{pawns:+.1f}"
