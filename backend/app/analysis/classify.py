"""Move classification from the winning-chances drop (SPEC §6.1)."""

from typing import Literal

from app.analysis.evals import Color, Evaluation, win_percent
from app.config import Thresholds

Classification = Literal["inaccuracy", "mistake", "blunder"]
SEVERITY_RANK: dict[Classification, int] = {"inaccuracy": 1, "mistake": 2, "blunder": 3}


def classify(drop: float, thresholds: Thresholds) -> Classification | None:
    """`drop` is the mover's winning-chances loss (wc scale, -1..1)."""
    if drop >= thresholds.blunder:
        return "blunder"
    if drop >= thresholds.mistake:
        return "mistake"
    if drop >= thresholds.inaccuracy:
        return "inaccuracy"
    return None


def is_missed_mate(
    before: Evaluation, after: Evaluation, mover: Color, thresholds: Thresholds
) -> bool:
    """The mover had a forced mate before the move, no longer has one (PLAN Q21), and the miss
    cost something: the mover's win% afterwards is below the configured cutoff."""
    if not _mover_mates(before, mover) or _mover_mates(after, mover):
        return False
    white_pct = win_percent(after)
    mover_pct = white_pct if mover == "white" else 100 - white_pct
    return mover_pct < thresholds.missed_mate_max_win_pct_after


def _mover_mates(evaluation: Evaluation, mover: Color) -> bool:
    if evaluation.checkmated is not None:
        return evaluation.checkmated != mover
    if evaluation.mate is None:
        return False
    return (evaluation.mate > 0) == (mover == "white")
