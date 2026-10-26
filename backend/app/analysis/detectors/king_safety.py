"""king_safety (SPEC §6.4 #5): on a mistake or worse, the user weakened the king's pawn shield
or opened a file beside it, or the reply line attacks the king with check (PLAN Q15)."""

import chess

from app.analysis.detectors.types import DetailValue, MoveContext, ThemeFact
from app.analysis.material import mate_position, material_swing


def detect(ctx: MoveContext) -> list[ThemeFact]:
    if not ctx.at_least("mistake"):
        return []
    board, user = ctx.board_before, ctx.side
    king = board.king(user)
    if king is None:
        return []

    details: dict[str, DetailValue] = {}
    if board.piece_type_at(ctx.move.from_square) == chess.PAWN:
        if _in_pawn_shield(king, ctx.move.from_square, user):
            details["pawn_moved"] = ctx.san
        opened = _opened_files(board, ctx.board_after, king, user)
        if opened:
            details["opened_files"] = opened
    checks = _check_sequence(ctx)
    if checks:
        details["check_sequence"] = checks
    return [ctx.fact("king_safety", details)] if details else []


def _in_pawn_shield(king: chess.Square, square: chess.Square, user: chess.Color) -> bool:
    """On the king's file or next to it, one or two ranks in front of the king."""
    ahead = chess.square_rank(square) - chess.square_rank(king)
    if user == chess.BLACK:
        ahead = -ahead
    return abs(chess.square_file(square) - chess.square_file(king)) <= 1 and 1 <= ahead <= 2


def _opened_files(
    before: chess.Board, after: chess.Board, king: chess.Square, user: chess.Color
) -> list[str]:
    king_file = chess.square_file(king)
    return [
        chess.FILE_NAMES[f]
        for f in (king_file - 1, king_file, king_file + 1)
        if 0 <= f < 8
        and _has_pawn_on_file(before, f, user)
        and not _has_pawn_on_file(after, f, user)
    ]


def _has_pawn_on_file(board: chess.Board, file: int, color: chess.Color) -> bool:
    return bool(board.pieces(chess.PAWN, color) & chess.BB_FILES[file])


def _check_sequence(ctx: MoveContext) -> list[str]:
    """The reply line's first plies if they check the king and the drop isn't a material grab."""
    plies, reply = ctx.settings.king_check_plies, ctx.best_line_after
    work = ctx.board_after.copy(stack=False)
    sans, gave_check = [], False
    for move in reply[:plies]:
        sans.append(work.san(move))
        gave_check = gave_check or (work.turn != ctx.side and work.gives_check(move))
        work.push(move)
    if not gave_check:
        return []
    mates = mate_position(ctx.board_after, reply, len(reply)) is not None
    grabbed = -material_swing(ctx.board_after, reply, plies, ctx.side)
    if not mates and grabbed >= ctx.settings.min_material_gain:
        return []
    return sans
