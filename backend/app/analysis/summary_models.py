"""The game summary schema (SPEC §6.5): stored per game and sent to the coach."""

from typing import Literal

from pydantic import BaseModel

from app.analysis.detectors.types import ThemeFact, ThemeName
from app.analysis.evals import Color
from app.analysis.phase import Phase

# A move's label: its classification, or "missed_mate" (unless it was also a blunder).
MoveLabel = Literal["inaccuracy", "mistake", "blunder", "missed_mate"]


class GameInfo(BaseModel):
    white: str
    black: str
    result: str
    time_control: str | None
    opening: str | None
    num_moves: int


class UserInfo(BaseModel):
    color: Color
    elo: int
    playstyle: str | None


class Accuracy(BaseModel):
    user: float | None
    opponent: float | None


class Counts(BaseModel):
    """The user's moves. A missed mate is also counted under its classification, if any."""

    inaccuracies: int
    mistakes: int
    blunders: int
    missed_mates: int


class PhaseStats(BaseModel):
    moves: int
    accuracy: float | None
    inaccuracies: int
    mistakes: int
    blunders: int


class EvalPoint(BaseModel):
    ply: int
    eval: str  # after the move at `ply`


class LineSummary(BaseModel):
    rank: int
    eval: str
    moves_san: list[str]


class KeyMoment(BaseModel):
    ply: int
    move_number: int
    side: Color
    move_san: str
    classification: MoveLabel | None
    eval_before: str
    eval_after: str
    best_move_san: str | None
    engine_lines: list[LineSummary]  # from the position before the move
    # The engine's best continuation after the move actually played: the refutation of a
    # mistake, or the punishment the other side should look for. Not in SPEC §6.5 (M3 review).
    line_after_san: list[str]
    themes: list[ThemeName]


class MoveEntry(BaseModel):
    ply: int
    move_number: int
    side: Color
    san: str
    eval_after: str
    classification: MoveLabel | None


class GameSummary(BaseModel):
    game: GameInfo
    user: UserInfo
    accuracy: Accuracy
    counts: Counts
    phase_breakdown: dict[Phase, PhaseStats]
    eval_curve: list[EvalPoint]
    key_moments: list[KeyMoment]
    theme_facts: list[ThemeFact]
    move_list: list[MoveEntry]
