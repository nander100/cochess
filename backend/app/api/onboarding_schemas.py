"""Request and response models for onboarding (SPEC_V2 §10, §11)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.analysis.onboarding import Category, Reason, Slot
from app.api.schemas import Color, GameStatus, PgnErrorDetail, TimeControl, UserResult

MAX_PASTE_GAMES = 40  # mirrors OnboardingSettings.max_paste_games; bounds the request's lists


class GameChoice(BaseModel):
    """What the player says about one game: their side, and the time control if the PGN has no
    TimeControl header (ignored when it does)."""

    user_color: Color | None = None
    time_control_category: TimeControl | None = None


class ParseRequest(BaseModel):
    pgn_text: str = Field(min_length=1)
    # One per game in the paste, by position; missing entries mean "not chosen yet".
    choices: list[GameChoice | None] = Field(default=[], max_length=MAX_PASTE_GAMES)


class ParsedRow(BaseModel):
    """One game of the paste, for the table (SPEC_V2 §10.3 step 3)."""

    index: int
    pgn: str | None  # the cleaned single-game PGN to submit; None if it can't be analyzed
    white: str | None
    black: str | None
    result: str | None
    date: str | None
    time_control: str | None  # the header
    category: Category | None  # from the header; None means the player picks
    error: PgnErrorDetail | None
    suggested_color: Color | None
    user_color: Color | None  # the player's choice, else the suggestion
    user_result: UserResult | None
    slot: Slot | None
    reason: Reason | None


class SlotCount(BaseModel):
    slot: Slot
    filled: int
    of: int


class ParseResponse(BaseModel):
    primary_time_control: TimeControl
    games: list[ParsedRow]
    slots: list[SlotCount]  # already filled, before this paste


class SubmitGame(BaseModel):
    pgn: str = Field(min_length=1)
    user_color: Color
    time_control_category: TimeControl | None = None


class SubmitRequest(BaseModel):
    games: list[SubmitGame] = Field(min_length=1, max_length=MAX_PASTE_GAMES)


class SubmitResult(BaseModel):
    index: int
    slot: Slot | None
    reason: Reason | None
    game_id: str | None  # the new game, when it filled a slot


class SubmitResponse(BaseModel):
    results: list[SubmitResult]
    slots: list[SlotCount]


class OnboardingGame(BaseModel):
    id: str
    slot: Slot
    status: GameStatus
    opponent: str
    played_at: datetime
    opening: str | None


class BaselineReport(BaseModel):
    text: str
    invalid_moves_removed: list[str]
    game_ids: list[str]
    created_at: datetime


class OnboardingStatus(BaseModel):
    primary_time_control: TimeControl | None
    slots: list[SlotCount]
    games: list[OnboardingGame]  # in upload order: the order they're analyzed
    complete: bool  # every slot filled
    analyzed: int
    report_ready: bool  # every slot filled and every game analyzed
    report: BaselineReport | None
