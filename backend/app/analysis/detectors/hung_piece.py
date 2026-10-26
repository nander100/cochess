"""hung_piece (SPEC §6.4 #1): the user's move leaves a piece loose, and the best reply wins it."""

import chess

from app.analysis.detectors.types import MoveContext, ThemeFact
from app.analysis.material import PIECE_VALUES, material_swing, value_at


def detect(ctx: MoveContext) -> list[ThemeFact]:
    if not ctx.flagged:
        return []
    board, user = ctx.board_after, ctx.side
    loose = [
        square
        for square, piece in board.piece_map().items()
        if piece.color == user and piece.piece_type != chess.KING and _is_loose(board, square)
    ]
    if not loose:
        return []

    window = ctx.settings.hung_piece_plies
    # Measured from before the user's move, so an even trade isn't reported as a hung piece.
    lost = -material_swing(ctx.board_before, (ctx.move, *ctx.best_line_after), 1 + window, user)
    if lost < ctx.settings.min_material_gain:
        return []

    square, lost_to = _capture_of(board, ctx.best_line_after[:window], loose, user)
    if square is None:
        square = max(loose, key=lambda s: value_at(board, s))
    piece_type = board.piece_type_at(square)
    assert piece_type is not None
    return [
        ctx.fact(
            "hung_piece",
            {
                "piece": chess.piece_name(piece_type),
                "square": chess.square_name(square),
                "lost_to": lost_to,
                "material_lost": lost,
            },
        )
    ]


def _is_loose(board: chess.Board, square: chess.Square) -> bool:
    """Attacked and undefended, or attacked by a cheaper piece (kings can't take defended men)."""
    piece = board.piece_at(square)
    assert piece is not None
    attackers = board.attackers(not piece.color, square)
    if not attackers:
        return False
    if not board.is_attacked_by(piece.color, square):
        return True
    values = [value_at(board, a) for a in attackers if board.piece_type_at(a) != chess.KING]
    return bool(values) and min(values) < PIECE_VALUES[piece.piece_type]


def _capture_of(
    board: chess.Board, line: tuple[chess.Move, ...], loose: list[chess.Square], user: chess.Color
) -> tuple[chess.Square | None, str | None]:
    """The reply line's capture of a loose piece, else its first capture of any user piece."""
    work = board.copy(stack=False)
    first: tuple[chess.Square | None, str | None] = (None, None)
    for move in line:
        if work.is_capture(move) and work.color_at(move.to_square) == user:
            if move.to_square in loose:
                return move.to_square, work.san(move)
            if first == (None, None):
                first = (None, work.san(move))
        work.push(move)
    return first
