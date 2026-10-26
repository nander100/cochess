import chess

from app.analysis.pawns import backward_pawns, doubled_files, isolated_files, passed_pawns


def test_doubled_and_isolated_files() -> None:
    board = chess.Board("4k3/8/8/8/8/4P3/4P1P1/4K3 w - - 0 1")  # e2, e3, g2

    assert doubled_files(board, chess.WHITE) == {"e"}
    assert isolated_files(board, chess.WHITE) == {"e", "g"}


def test_connected_pawns_are_not_isolated() -> None:
    assert isolated_files(chess.Board(), chess.WHITE) == frozenset()


def test_passed_pawns_have_no_enemy_pawns_ahead_on_adjacent_files() -> None:
    board = chess.Board("4k3/p7/8/8/8/8/6P1/4K3 w - - 0 1")  # white g2, black a7

    assert passed_pawns(board, chess.WHITE) == {chess.G2}
    assert passed_pawns(board, chess.BLACK) == {chess.A7}


def test_blocked_by_an_adjacent_enemy_pawn_is_not_passed() -> None:
    board = chess.Board("4k3/5p2/8/8/8/8/6P1/4K3 w - - 0 1")  # black f7 guards g-file

    assert passed_pawns(board, chess.WHITE) == frozenset()


def test_backward_pawn_cannot_be_supported_and_its_advance_square_is_covered() -> None:
    board = chess.Board("4k3/8/8/4p3/2P5/3P4/8/4K3 w - - 0 1")  # d3 behind c4; e5 covers d4

    assert backward_pawns(board, chess.WHITE) == {chess.D3}


def test_supported_pawn_is_not_backward() -> None:
    board = chess.Board("4k3/8/8/4p3/8/2PP4/8/4K3 w - - 0 1")  # c3 sits beside d3

    assert backward_pawns(board, chess.WHITE) == frozenset()
