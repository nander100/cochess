"""missed_tactic (SPEC §6.4 #3): the best line wins >= 2 points or mates within 5 plies, and the
user played something else (PLAN Q13). Subtype from the shape of the best move."""

import chess

from app.analysis.detectors.types import MoveContext, ThemeFact
from app.analysis.material import line_to_san, mate_position, material_swing, value_at

_SLIDERS = (chess.BISHOP, chess.ROOK, chess.QUEEN)
_VALUABLE = 3  # discovered attacks count when they hit a minor piece or better (or the king)


def detect(ctx: MoveContext) -> list[ThemeFact]:
    if not ctx.flagged or not ctx.best_line_before:
        return []
    board, line, user = ctx.board_before, ctx.best_line_before, ctx.side
    if ctx.move == line[0]:
        return []
    plies = ctx.settings.tactic_plies
    mated = mate_position(board, line, plies)
    gain = material_swing(board, line, plies, user)
    if mated is None and gain < ctx.settings.min_material_gain:
        return []
    return [
        ctx.fact(
            "missed_tactic",
            {
                "subtype": subtype(board, line, mated, user, plies),
                "best_move": board.san(line[0]),
                "line": line_to_san(board, line[:plies]),
                "material_won": None if mated else gain,
                "forces_mate": mated is not None,
            },
        )
    ]


def subtype(
    board: chess.Board,
    line: tuple[chess.Move, ...],
    mated: chess.Board | None,
    user: chess.Color,
    plies: int,
) -> str:
    best = line[0]
    after = board.copy(stack=False)
    after.push(best)
    if _back_rank(board, line, mated, user):
        return "back_rank"
    if _is_fork(after, best.to_square, user):
        return "fork"
    line_attack = _pin_or_skewer(after, best.to_square, user)
    if line_attack:
        return line_attack
    if _is_discovered(board, after, best, user):
        return "discovered_attack"
    return "combination"


def _back_rank_of(color: chess.Color) -> int:
    return 0 if color == chess.WHITE else 7


def _back_rank(
    board: chess.Board,
    line: tuple[chess.Move, ...],
    mated: chess.Board | None,
    user: chess.Color,
) -> bool:
    """Mate with the king on its back rank, or a line that starts with a rook/queen check along
    the opponent's back rank. A back-rank check later in the line is usually just the capture
    that cashes in some other tactic (e.g. the Qxd8+ after a queen fork), so it doesn't count."""
    opponent_rank = _back_rank_of(not user)
    if mated is not None:
        king = mated.king(not user)
        return king is not None and chess.square_rank(king) == opponent_rank
    first = line[0]
    heavy = board.piece_type_at(first.from_square) in (chess.ROOK, chess.QUEEN)
    return (
        heavy and chess.square_rank(first.to_square) == opponent_rank and board.gives_check(first)
    )


def _is_fork(after: chess.Board, square: chess.Square, user: chess.Color) -> bool:
    """The moved piece attacks the king plus a piece, or two pieces worth >= it or undefended."""
    piece = after.piece_at(square)
    assert piece is not None
    if piece.piece_type == chess.KING:
        return False
    own_value = value_at(after, square)
    targets = [t for t in after.attacks(square) if after.color_at(t) == (not user)]
    king_hit = any(after.piece_type_at(t) == chess.KING for t in targets)
    others = [
        t
        for t in targets
        if after.piece_type_at(t) != chess.KING
        and (value_at(after, t) >= own_value or not after.is_attacked_by(not user, t))
    ]
    return (king_hit and len(others) >= 1) or len(others) >= 2


def _pin_or_skewer(after: chess.Board, square: chess.Square, user: chess.Color) -> str | None:
    if after.piece_type_at(square) not in _SLIDERS:
        return None
    for target in after.attacks(square):
        if after.color_at(target) != (not user):
            continue
        behind = _first_piece_behind(after, square, target)
        if behind is None or after.color_at(behind) != (not user):
            continue
        front, back = after.piece_type_at(target), after.piece_type_at(behind)
        if front == chess.KING:
            return "skewer"
        if back == chess.KING or value_at(after, behind) > value_at(after, target):
            return "pin"
        if value_at(after, target) > value_at(after, behind):
            return "skewer"
    return None


def _first_piece_behind(
    board: chess.Board, origin: chess.Square, target: chess.Square
) -> chess.Square | None:
    """The first occupied square past `target` on the line from `origin` through it."""
    beyond = [
        s
        for s in chess.SquareSet(chess.ray(origin, target))
        if s not in (origin, target)
        and board.piece_at(s) is not None
        and target in chess.SquareSet(chess.between(origin, s))
    ]
    return min(beyond, key=lambda s: chess.square_distance(target, s)) if beyond else None


def _is_discovered(
    before: chess.Board, after: chess.Board, best: chess.Move, user: chess.Color
) -> bool:
    """Moving the piece uncovers a line piece's attack on the king or a piece worth >= 3."""
    for square in chess.SquareSet(after.occupied_co[user]):
        if square == best.to_square or after.piece_type_at(square) not in _SLIDERS:
            continue
        for target in after.attacks(square):
            if target in before.attacks(square) or after.color_at(target) != (not user):
                continue
            hits_king = after.piece_type_at(target) == chess.KING
            if (hits_king or value_at(after, target) >= _VALUABLE) and best.from_square in (
                chess.SquareSet(chess.between(square, target))
            ):
                return True
    return False
