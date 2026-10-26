"""Request and response models for the HTTP API (SPEC §9)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.analysis.engine import EngineResult
from app.analysis.pgn import PgnErrorCode, Position
from app.analysis.summary_models import Accuracy, Counts

# Input rules from SPEC §3 (user flow), not tunable thresholds.
MIN_ELO = 100
MAX_ELO = 3000
MAX_PLAYSTYLE_CHARS = 500

Color = Literal["white", "black"]


class CreateGameRequest(BaseModel):
    pgn: str = Field(min_length=1)
    user_color: Color
    elo: int = Field(ge=MIN_ELO, le=MAX_ELO)
    playstyle: str | None = Field(default=None, max_length=MAX_PLAYSTYLE_CHARS)

    @field_validator("playstyle")
    @classmethod
    def blank_playstyle_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


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
