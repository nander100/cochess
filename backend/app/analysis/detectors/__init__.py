"""Theme detectors (SPEC §6.4, plus allowed_tactic). Each is pure: (context) -> list[ThemeFact]."""

from collections.abc import Callable

from app.analysis.detectors import (
    allowed_tactic,
    endgame_technique,
    hung_piece,
    king_safety,
    missed_capture_or_check,
    missed_tactic,
    pawn_structure,
    slow_development,
    time_trouble,
)
from app.analysis.detectors.types import GameContext, MoveContext, ThemeFact

PER_MOVE: tuple[Callable[[MoveContext], list[ThemeFact]], ...] = (
    hung_piece.detect,
    allowed_tactic.detect,
    missed_capture_or_check.detect,
    missed_tactic.detect,
    king_safety.detect,
    pawn_structure.detect,
    endgame_technique.detect,
)
GAME_LEVEL: tuple[Callable[[GameContext], list[ThemeFact]], ...] = (
    slow_development.detect,
    pawn_structure.detect_game,
    time_trouble.detect,
)


def run_detectors(game: GameContext) -> list[ThemeFact]:
    facts: list[ThemeFact] = []
    for move in game.user_moves():
        if move.flagged:  # SPEC §6.3: per-move detectors only fire on inaccuracies or worse
            for detect in PER_MOVE:
                facts.extend(detect(move))
    for detect_game in GAME_LEVEL:
        facts.extend(detect_game(game))
    return facts
