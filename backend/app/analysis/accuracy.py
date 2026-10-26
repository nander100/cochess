"""Lichess accuracy (lila `AccuracyPercent`, PLAN Q11).

Per move: 103.1668 * exp(-0.04354 * win% lost) - 3.1669, plus a 1-point uncertainty bonus,
clamped to 0..100. A side's accuracy is the mean of a volatility-weighted mean and a harmonic
mean of its per-move accuracies; weights are the standard deviation of win% over a sliding
window, so moves in sharp positions count more.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from app.analysis.evals import Color

_A = 103.1668100711649
_K = 0.04354415386753951
_B = 3.166924740191411
_UNCERTAINTY_BONUS = 1.0
_MIN_WINDOW, _MAX_WINDOW = 2, 8
_MIN_WEIGHT, _MAX_WEIGHT = 0.5, 12.0


@dataclass(frozen=True)
class MoveAccuracy:
    ply: int
    color: Color
    accuracy: float
    weight: float


def move_accuracy(win_pct_before: float, win_pct_after: float) -> float:
    """Accuracy of one move from the mover's win% before and after (both mover POV)."""
    if win_pct_after >= win_pct_before:
        return 100.0
    raw = _A * math.exp(-_K * (win_pct_before - win_pct_after)) - _B + _UNCERTAINTY_BONUS
    return max(0.0, min(100.0, raw))


def move_accuracies(white_win_pcts: Sequence[float]) -> list[MoveAccuracy]:
    """Per-move accuracies and volatility weights. `white_win_pcts[i]` is White's win% before
    ply i + 1; the last entry is the final position."""
    moves = len(white_win_pcts) - 1
    if moves < 1:
        return []
    size = max(_MIN_WINDOW, min(_MAX_WINDOW, moves // 10))
    sliding = [white_win_pcts[i : i + size] for i in range(max(1, len(white_win_pcts) - size + 1))]
    windows = [white_win_pcts[:size]] * (size - 2) + sliding
    windows += [windows[-1]] * (moves - len(windows))  # very short games

    result = []
    for index in range(moves):
        ply = index + 1
        color: Color = "white" if ply % 2 == 1 else "black"
        before, after = white_win_pcts[index], white_win_pcts[index + 1]
        if color == "black":
            before, after = 100 - before, 100 - after
        weight = max(_MIN_WEIGHT, min(_MAX_WEIGHT, statistics.pstdev(windows[index])))
        result.append(MoveAccuracy(ply, color, move_accuracy(before, after), weight))
    return result


def aggregate(moves: Sequence[MoveAccuracy]) -> float | None:
    """(volatility-weighted mean + harmonic mean) / 2. None if there are no moves."""
    if not moves:
        return None
    weighted = sum(m.accuracy * m.weight for m in moves) / sum(m.weight for m in moves)
    if any(m.accuracy == 0 for m in moves):
        harmonic = 0.0
    else:
        harmonic = len(moves) / sum(1 / m.accuracy for m in moves)
    return (weighted + harmonic) / 2
