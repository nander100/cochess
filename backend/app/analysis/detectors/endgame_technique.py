"""endgame_technique (SPEC §6.4 #7): mistakes or worse in the endgame, by subtype."""

import chess

from app.analysis.detectors.types import MoveContext, ThemeFact
from app.analysis.material import center_distance
from app.analysis.pawns import passed_pawns


def detect(ctx: MoveContext) -> list[ThemeFact]:
    if ctx.phase != "endgame" or not ctx.at_least("mistake"):
        return []
    settings, user = ctx.settings, ctx.side
    facts = []

    before_pct, after_pct = ctx.win_pct_before(), ctx.win_pct_after()
    if before_pct >= settings.threw_win_from_pct and after_pct <= settings.threw_win_to_pct:
        facts.append(
            ctx.fact(
                "endgame_technique",
                {
                    "subtype": "threw_win",
                    "win_pct_before": round(before_pct, 1),
                    "win_pct_after": round(after_pct, 1),
                },
            )
        )

    king = ctx.board_before.king(user)
    best = ctx.best_line_before[0] if ctx.best_line_before else None
    if (
        best is not None
        and best != ctx.move
        and king is not None
        and ctx.board_before.piece_type_at(best.from_square) == chess.KING
        and center_distance(king) >= settings.passive_king_center_distance
    ):
        facts.append(
            ctx.fact(
                "endgame_technique",
                {
                    "subtype": "passive_king",
                    "king_square": chess.square_name(king),
                    "best_move": ctx.board_before.san(best),
                },
            )
        )

    new_passers = passed_pawns(ctx.board_after, not user) - passed_pawns(ctx.board_before, not user)
    if new_passers:
        facts.append(
            ctx.fact(
                "endgame_technique",
                {
                    "subtype": "allowed_passer",
                    "squares": sorted(chess.square_name(s) for s in new_passers),
                },
            )
        )
    return facts
