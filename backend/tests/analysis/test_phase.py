import chess

from app.analysis.phase import game_phase, is_endgame
from app.config import DetectorSettings

SETTINGS = DetectorSettings()


def test_opening_until_ply_20() -> None:
    assert game_phase(chess.Board(), 20, SETTINGS) == "opening"
    assert game_phase(chess.Board(), 21, SETTINGS) == "middlegame"


def test_endgame_when_non_pawn_material_is_at_most_26() -> None:
    exactly_26 = chess.Board("1r1rb1k1/pppppppp/8/8/8/8/PPPPPPPP/1R1RB1K1 w - - 0 1")  # R R B each
    over = chess.Board("1rqrb1k1/pppppppp/8/8/8/8/PPPPPPPP/1RQRB1K1 w - - 0 1")

    assert is_endgame(exactly_26, SETTINGS)
    assert not is_endgame(over, SETTINGS)


def test_an_early_endgame_is_still_endgame() -> None:
    board = chess.Board("8/8/8/4k3/8/8/4P3/4K3 w - - 0 1")

    assert game_phase(board, 5, SETTINGS) == "endgame"
