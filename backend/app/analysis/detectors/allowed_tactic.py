"""allowed_tactic (owner-approved addition at the M3 review, not in SPEC §6.4): the user's
mistake lets the opponent win >= 2 points or mate within 5 plies with their best reply.
Subtypes are the same as missed_tactic's, seen from the opponent's side. Moves already explained
by hung_piece are skipped so one mistake isn't reported twice."""

from app.analysis.detectors import hung_piece
from app.analysis.detectors.missed_tactic import subtype
from app.analysis.detectors.types import MoveContext, ThemeFact
from app.analysis.material import line_to_san, mate_position, material_swing


def detect(ctx: MoveContext) -> list[ThemeFact]:
    if not ctx.at_least("mistake") or not ctx.best_line_after:
        return []
    if hung_piece.detect(ctx):
        return []
    board, reply, opponent = ctx.board_after, ctx.best_line_after, not ctx.side
    plies = ctx.settings.tactic_plies
    mated = mate_position(board, reply, plies)
    lost = material_swing(board, reply, plies, opponent)
    if mated is None and lost < ctx.settings.min_material_gain:
        return []
    return [
        ctx.fact(
            "allowed_tactic",
            {
                "subtype": subtype(board, reply, mated, opponent, plies),
                "reply_move": board.san(reply[0]),
                "line": line_to_san(board, reply[:plies]),
                "material_lost": None if mated else lost,
                "allows_mate": mated is not None,
            },
        )
    ]
