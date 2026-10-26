"""Game phase of a position (SPEC §6.2)."""

from typing import Literal

import chess

from app.analysis.material import non_pawn_material
from app.config import DetectorSettings

Phase = Literal["opening", "middlegame", "endgame"]
PHASES: tuple[Phase, ...] = ("opening", "middlegame", "endgame")


def is_endgame(board: chess.Board, settings: DetectorSettings) -> bool:
    """Little non-pawn material left, or queens off with each side down to <= 1 rook and 1 minor."""
    total = non_pawn_material(board, chess.WHITE) + non_pawn_material(board, chess.BLACK)
    if total <= settings.endgame_max_non_pawn_material:
        return True
    if board.pieces(chess.QUEEN, chess.WHITE) or board.pieces(chess.QUEEN, chess.BLACK):
        return False
    return all(
        len(board.pieces(chess.ROOK, color)) <= 1
        and len(board.pieces(chess.KNIGHT, color)) + len(board.pieces(chess.BISHOP, color)) <= 1
        for color in chess.COLORS
    )


def game_phase(board: chess.Board, ply: int, settings: DetectorSettings) -> Phase:
    """Phase of the position before the move at `ply`."""
    if is_endgame(board, settings):
        return "endgame"
    return "opening" if ply <= settings.opening_max_ply else "middlegame"
