"""Critical moments (SPEC_V2 §8): choosing them from the game's analysis."""

from collections.abc import Sequence

from app.analysis.detectors.types import GameContext, MoveContext, ThemeFact
from app.analysis.evals import format_eval
from app.analysis.material import line_to_san
from app.analysis.moves import label
from app.analysis.summary_models import Moment
from app.config import MomentSettings

_ERRORS = frozenset({"mistake", "blunder", "missed_mate"})


def select_moments(
    context: GameContext, facts: Sequence[ThemeFact], settings: MomentSettings
) -> list[Moment]:
    """SPEC_V2 §8.1: every mistake, blunder and missed mate; topped up with the biggest
    inaccuracies to `min_moments`; capped at `max_moments` keeping the biggest drops; in game
    order."""
    user_moves = context.user_moves()
    chosen = [m for m in user_moves if label(m) in _ERRORS]
    if len(chosen) < settings.min_moments:
        inaccuracies = sorted(
            (m for m in user_moves if label(m) == "inaccuracy"), key=lambda m: (-m.drop, m.ply)
        )
        chosen += inaccuracies[: settings.min_moments - len(chosen)]
    if len(chosen) > settings.max_moments:
        chosen = sorted(chosen, key=lambda m: (-m.drop, m.ply))[: settings.max_moments]
    ordered = sorted(chosen, key=lambda m: m.ply)
    return [_moment(index, move, facts, settings) for index, move in enumerate(ordered, start=1)]


def _moment(
    index: int, move: MoveContext, facts: Sequence[ThemeFact], settings: MomentSettings
) -> Moment:
    move_label = label(move)
    assert move_label is not None  # only labelled moves are chosen
    return Moment(
        index=index,
        ply=move.ply,
        move_number=move.move_number,
        side=move.color,
        san=move.san,
        uci=move.move.uci(),
        label=move_label,
        drop=round(move.drop, 4),
        eval_before=format_eval(move.eval_before),
        eval_after=format_eval(move.eval_after),
        themes=sorted({f.theme for f in facts if f.ply == move.ply}),
        refutation_san=line_to_san(
            move.board_after, move.best_line_after[: settings.refutation_plies]
        ),
        fen_before=move.board_before.fen(),
    )
