import chess

from app.analysis.material import (
    balance,
    center_distance,
    line_to_san,
    mate_position,
    material,
    material_swing,
    non_pawn_material,
)
from tests.detector_helpers import san_line

AFTER_E4_D5 = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2"


def test_material_counts_pieces_by_value() -> None:
    board = chess.Board()

    assert material(board, chess.WHITE) == 8 + 2 * 3 + 2 * 3 + 2 * 5 + 9
    assert non_pawn_material(board, chess.BLACK) == 31
    assert balance(board, chess.WHITE) == 0


def test_material_swing_counts_the_recapture_after_a_capture() -> None:
    board = chess.Board(AFTER_E4_D5)
    line = san_line(board, ["exd5", "Qxd5", "Nc3"])

    # Stopping after exd5 would show +1; the window extends to the recapture.
    assert material_swing(board, line, 1, chess.WHITE) == 0


def test_material_swing_measures_a_won_piece() -> None:
    board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/4P2q/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")

    assert material_swing(board, san_line(board, ["Nxh4"]), 3, chess.WHITE) == 9


def test_mate_position_finds_a_mate_inside_the_window() -> None:
    board = chess.Board("6k1/5ppp/8/8/8/8/8/3R2K1 w - - 0 1")
    line = san_line(board, ["Rd8#"])

    mated = mate_position(board, line, 5)

    assert mated is not None and mated.is_checkmate()
    assert mate_position(board, (), 5) is None


def test_line_to_san_does_not_mutate_the_board() -> None:
    board = chess.Board()

    assert line_to_san(board, san_line(board, ["e4", "e5", "Nf3"])) == ["e4", "e5", "Nf3"]
    assert board.fen() == chess.STARTING_FEN


def test_center_distance() -> None:
    assert center_distance(chess.E1) == 3
    assert center_distance(chess.D4) == 0
    assert center_distance(chess.H8) == 3
