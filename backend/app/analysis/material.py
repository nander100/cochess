"""Material counting and engine-line walking helpers. Pure functions; boards are never mutated."""

from collections.abc import Sequence

import chess

PIECE_VALUES: dict[chess.PieceType, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
CENTER = (chess.D4, chess.D5, chess.E4, chess.E5)


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(len(board.pieces(kind, color)) * value for kind, value in PIECE_VALUES.items())


def non_pawn_material(board: chess.Board, color: chess.Color) -> int:
    return material(board, color) - len(board.pieces(chess.PAWN, color))


def balance(board: chess.Board, color: chess.Color) -> int:
    """`color`'s material minus the opponent's."""
    return material(board, color) - material(board, not color)


def value_at(board: chess.Board, square: chess.Square) -> int:
    piece = board.piece_at(square)
    return PIECE_VALUES[piece.piece_type] if piece else 0


def material_swing(
    board: chess.Board, moves: Sequence[chess.Move], plies: int, color: chess.Color
) -> int:
    """Change in `color`'s material balance over the first `plies` moves of a line.

    If the last counted move is a capture and the line continues, the reply is counted too, so
    an exchange isn't measured halfway through (PLAN Q14).
    """
    work = board.copy(stack=False)
    start = balance(work, color)
    count = min(plies, len(moves))
    last_was_capture = False
    for move in moves[:count]:
        last_was_capture = work.is_capture(move)
        work.push(move)
    if last_was_capture and count < len(moves):
        work.push(moves[count])
    return balance(work, color) - start


def mate_position(
    board: chess.Board, moves: Sequence[chess.Move], plies: int
) -> chess.Board | None:
    """The checkmated board if the line mates within `plies` moves, else None."""
    work = board.copy(stack=False)
    for move in moves[:plies]:
        work.push(move)
        if work.is_checkmate():
            return work
    return None


def line_to_san(board: chess.Board, moves: Sequence[chess.Move]) -> list[str]:
    work = board.copy(stack=False)
    sans = []
    for move in moves:
        sans.append(work.san(move))
        work.push(move)
    return sans


def center_distance(square: chess.Square) -> int:
    """King-move distance from `square` to the nearest of d4, d5, e4, e5."""
    return min(chess.square_distance(square, center) for center in CENTER)
