"""Where line playback stops, and what the caption says there (SPEC_V3 §9.5, §9.6).

Deterministic, never the LLM: the first ply (at least `min_plies` in, so the reply is shown)
where the starting player's win% has moved enough or material has changed enough, and the
position is quiet (no check, and the next move isn't a capture, so playback never stops in the
middle of an exchange). Checkmate stops at once. The caption compares the start and the stop.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import chess

from app.analysis.evals import Evaluation, win_percent
from app.analysis.material import PIECE_VALUES, balance
from app.analysis.move_facts import PIECE_NAMES
from app.analysis.pawns import passed_pawns
from app.config import PlaybackSettings

NUMBERS = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
ORDER = (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN)


@dataclass(frozen=True)
class Settled:
    settle_ply: int  # 1-based: stop after this many moves of the line
    caption: str


def settle(
    start_fen: str,
    moves: Sequence[str],
    evals: Sequence[Evaluation | None],
    min_plies: int,
    settings: PlaybackSettings,
) -> Settled:
    """`evals[0]` is the start's evaluation and `evals[k]` the one after move k (None when
    unknown: then only material counts for that ply). Raises ValueError for an empty line, a
    wrong number of evals, or an illegal move."""
    if not moves or len(evals) != len(moves) + 1:
        raise ValueError("a line of at least one move, and one evaluation per position")
    start = chess.Board(start_fen)
    side = start.turn
    boards = _boards(start, moves)
    start_win = _win(evals[0], side)
    start_material = balance(start, side)
    stop = len(moves)
    for k in range(1, len(moves) + 1):
        board = boards[k]
        if board.is_checkmate():
            stop = k
            break
        if k < min_plies:
            continue
        win = _win(evals[k], side)
        swung = (
            start_win is not None
            and win is not None
            and abs(win - start_win) >= settings.settle_win_pct
        )
        moved = swung or abs(balance(board, side) - start_material) >= settings.settle_material
        next_is_capture = k < len(moves) and board.is_capture(chess.Move.from_uci(moves[k]))
        if moved and not board.is_check() and not next_is_capture:
            stop = k
            break
    return Settled(stop, caption(start, boards[stop], evals[stop], settings))


def _boards(start: chess.Board, moves: Sequence[str]) -> list[chess.Board]:
    boards = [start.copy(stack=False)]
    board = start.copy(stack=False)
    for uci in moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"{uci} is not legal in {board.fen()}")
        board.push(move)
        boards.append(board.copy(stack=False))
    return boards


def _win(evaluation: Evaluation | None, side: chess.Color) -> float | None:
    if evaluation is None:
        return None
    white = win_percent(evaluation)
    return white if side == chess.WHITE else 100 - white


def caption(
    start: chess.Board, stop: chess.Board, evaluation: Evaluation | None, settings: PlaybackSettings
) -> str:
    """What changed between the start and the stop, from the boards: checkmate, material, a new
    passed pawn, else the evaluation in words."""
    if stop.is_checkmate():
        return f"{_name(stop.turn)} is checkmated."
    material = _material(start, stop)
    if material is not None:
        return material
    for color in (chess.WHITE, chess.BLACK):
        if len(passed_pawns(stop, color)) > len(passed_pawns(start, color)):
            return f"{_name(color)} now has a passed pawn."
    return _standing(evaluation, settings)


def _material(start: chess.Board, stop: chess.Board) -> str | None:
    lost = {color: _lost(start, stop, color) for color in (chess.WHITE, chess.BLACK)}
    points = {color: sum(PIECE_VALUES[t] * n for t, n in lost[color].items()) for color in lost}
    if abs(points[chess.WHITE] - points[chess.BLACK]) < 2:
        return None
    winner = chess.WHITE if points[chess.WHITE] < points[chess.BLACK] else chess.BLACK
    won, gave = _pieces(lost[not winner]), _pieces(lost[winner])
    return f"{_name(winner)} has won {won}" + (f" for {gave}." if gave else ".")


def _lost(start: chess.Board, stop: chess.Board, color: chess.Color) -> Counter[chess.PieceType]:
    """Pieces `color` had at the start and not at the stop (promotions aside)."""
    counts: Counter[chess.PieceType] = Counter()
    for kind in ORDER:
        gone = len(start.pieces(kind, color)) - len(stop.pieces(kind, color))
        if gone > 0:
            counts[kind] = gone
    return counts


def _pieces(counts: Counter[chess.PieceType]) -> str:
    parts = []
    for kind in ORDER:
        n = counts.get(kind, 0)
        if n:
            parts.append(f"{NUMBERS.get(n, str(n))} {PIECE_NAMES[kind]}{'s' if n > 1 else ''}")
    return " and ".join(parts)


def _standing(evaluation: Evaluation | None, settings: PlaybackSettings) -> str:
    if evaluation is None:
        return "The position has settled."
    white = win_percent(evaluation)
    leader, pct = ("White", white) if white >= 50 else ("Black", 100 - white)
    if pct >= settings.winning_pct:
        return f"{leader} is winning."
    if pct >= settings.clearly_better_pct:
        return f"{leader} is clearly better."
    if pct >= settings.slightly_better_pct:
        return f"{leader} is slightly better."
    return "The position is about equal."


def _name(color: chess.Color) -> str:
    return "White" if color == chess.WHITE else "Black"
