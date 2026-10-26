"""missed_capture_or_check (SPEC §6.4 #2): the best move was a capture or check; the user's
mistake was neither."""

from app.analysis.detectors.types import MoveContext, ThemeFact
from app.analysis.material import material_swing


def detect(ctx: MoveContext) -> list[ThemeFact]:
    if not ctx.at_least("mistake") or not ctx.best_line_before:
        return []
    board, best = ctx.board_before, ctx.best_line_before[0]
    is_capture, is_check = board.is_capture(best), board.gives_check(best)
    if not (is_capture or is_check) or ctx.move == best:
        return []
    if board.is_capture(ctx.move) or board.gives_check(ctx.move):
        return []

    # Same window as missed_tactic: a 10-ply line can give the material back at its very end.
    won = material_swing(board, ctx.best_line_before, ctx.settings.tactic_plies, ctx.side)
    kind = "capture_and_check" if is_capture and is_check else "capture" if is_capture else "check"
    return [
        ctx.fact(
            "missed_capture_or_check",
            {"best_move": board.san(best), "kind": kind, "material_won": max(won, 0)},
        )
    ]
