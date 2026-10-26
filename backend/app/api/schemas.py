"""Request and response models for the HTTP API (SPEC §9)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.analysis.engine import EngineResult
from app.analysis.pgn import PgnErrorCode, Position
from app.analysis.summary_models import Accuracy, Counts

# Profile input rules from SPEC_V2 §4.3, not tunable thresholds.
MIN_ELO = 100
MAX_ELO = 3000
MAX_PLAYSTYLE_CHARS = 500
MAX_NAME_CHARS = 60

Color = Literal["white", "black"]
TimeControl = Literal["bullet", "blitz", "rapid", "classical"]


class CreateGameRequest(BaseModel):
    """Elo and playstyle come from the player's profile (SPEC_V2 §4.3)."""

    pgn: str = Field(min_length=1)
    user_color: Color


class Profile(BaseModel):
    name: str
    elo: int | None
    time_control: TimeControl | None
    playstyle: str | None
    # Elo and time control are needed before analyzing games; playstyle is optional.
    complete: bool


class ProfileUpdate(BaseModel):
    """PATCH /api/me: only the fields sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_CHARS)
    elo: int | None = Field(default=None, ge=MIN_ELO, le=MAX_ELO)
    time_control: TimeControl | None = None
    playstyle: str | None = Field(default=None, max_length=MAX_PLAYSTYLE_CHARS)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Your name can't be blank.")
        return value.strip()

    @field_validator("playstyle")
    @classmethod
    def blank_playstyle_is_empty(cls, value: str | None) -> str | None:
        # A blank playstyle clears it; None (not sent) leaves it as it is.
        return None if value is None else value.strip()


class CreateGameResponse(BaseModel):
    game_id: str
    positions: list[Position]
    final_fen: str
    final_is_terminal: bool


class PgnErrorDetail(BaseModel):
    code: PgnErrorCode
    message: str
    move_number: int | None


class PgnErrorResponse(BaseModel):
    detail: PgnErrorDetail


class EngineResultsRequest(BaseModel):
    results: list[EngineResult]


class ScanResponse(BaseModel):
    verify_fens: list[str]


class VerifyResponse(BaseModel):
    summary_ready: bool
    counts: Counts | None
    accuracy: Accuracy | None
