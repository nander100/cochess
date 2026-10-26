"""Detector inputs and outputs (SPEC §6.3). Detectors are pure: (context) -> list[ThemeFact]."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import chess
from pydantic import BaseModel, ConfigDict

from app.analysis.classify import SEVERITY_RANK, Classification
from app.analysis.evals import Color, Evaluation, format_eval, win_percent
from app.analysis.phase import Phase
from app.config import DetectorSettings

ThemeName = Literal[
    "hung_piece",
    "missed_capture_or_check",
    "missed_tactic",
    "slow_development",
    "king_safety",
    "pawn_structure",
    "endgame_technique",
    "time_trouble",
    "allowed_tactic",  # owner-approved addition (M3 review)
]
# Per-move facts carry the move's classification; game-level facts are "note" or "concern".
Severity = Literal["inaccuracy", "mistake", "blunder", "note", "concern"]
DetailValue = str | int | float | bool | list[str] | None


class ThemeFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    theme: ThemeName
    ply: int | None = None
    move_number: int | None = None
    move_san: str | None = None
    severity: Severity
    eval_before: str | None = None
    eval_after: str | None = None
    details: dict[str, DetailValue]


@dataclass(frozen=True)
class MoveContext:
    """One ply of the game. Boards are shared snapshots: detectors must copy before pushing."""

    ply: int
    move_number: int
    color: Color  # the side that moved
    move: chess.Move
    san: str
    board_before: chess.Board
    board_after: chess.Board
    classification: Classification | None
    missed_mate: bool
    drop: float  # the mover's winning-chances loss
    eval_before: Evaluation
    eval_after: Evaluation
    best_line_before: tuple[chess.Move, ...]  # engine's best line from the position before
    best_line_after: tuple[chess.Move, ...]  # the opponent's best reply line
    phase: Phase
    clock_s: float | None
    settings: DetectorSettings

    @property
    def side(self) -> chess.Color:
        return chess.WHITE if self.color == "white" else chess.BLACK

    @property
    def flagged(self) -> bool:
        """Inaccuracy or worse, or a missed mate: the moves per-move detectors look at."""
        return self.classification is not None or self.missed_mate

    def at_least(self, level: Classification) -> bool:
        """A missed mate counts as at least a mistake."""
        if self.missed_mate and SEVERITY_RANK[level] <= SEVERITY_RANK["mistake"]:
            return True
        if self.classification is None:
            return False
        return SEVERITY_RANK[self.classification] >= SEVERITY_RANK[level]

    def win_pct_before(self) -> float:
        return self._for_mover(win_percent(self.eval_before))

    def win_pct_after(self) -> float:
        return self._for_mover(win_percent(self.eval_after))

    def fact(self, theme: ThemeName, details: dict[str, DetailValue]) -> ThemeFact:
        return ThemeFact(
            theme=theme,
            ply=self.ply,
            move_number=self.move_number,
            move_san=self.san,
            severity=self.classification or "mistake",
            eval_before=format_eval(self.eval_before),
            eval_after=format_eval(self.eval_after),
            details=details,
        )

    def _for_mover(self, white_pct: float) -> float:
        return white_pct if self.color == "white" else 100 - white_pct


@dataclass(frozen=True)
class GameContext:
    user_color: Color
    moves: tuple[MoveContext, ...]  # every ply, both sides
    headers: Mapping[str, str]
    final_board: chess.Board
    settings: DetectorSettings

    def user_moves(self) -> tuple[MoveContext, ...]:
        return tuple(m for m in self.moves if m.color == self.user_color)


def game_fact(
    theme: ThemeName, severity: Literal["note", "concern"], details: dict[str, DetailValue]
) -> ThemeFact:
    return ThemeFact(theme=theme, severity=severity, details=details)
