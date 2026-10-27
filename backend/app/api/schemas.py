"""Request and response models for the HTTP API (SPEC §9)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.analysis.engine import EngineResult, Tier
from app.analysis.pgn import PgnErrorCode, Position
from app.analysis.summary_models import Accuracy, Counts, GameInfo, MoveLabel
from app.db.chat import ChatEntry

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


GameStatus = Literal["uploaded", "scanned", "analyzed"]
UserResult = Literal["win", "loss", "draw"]


class GameListItem(BaseModel):
    """One row of "My games" (SPEC_V2 §11)."""

    id: str
    played_at: datetime
    opponent: str
    user_color: Color
    user_result: UserResult | None
    time_control: str | None  # the PGN TimeControl header, e.g. "600+5"
    opening: str | None
    accuracy: float | None  # the player's, once analyzed
    status: GameStatus


class MoveInfo(BaseModel):
    """One ply of the game, with its analysis once the engine has run."""

    ply: int
    move_number: int
    side: Color
    san: str
    uci: str
    fen_before: str
    clock_s: float | None
    eval_after: str | None  # display format, "+0.3" / "-M2"
    win_pct_after: float | None  # White's win% after the move, 0..100
    label: MoveLabel | None  # inaccuracy / mistake / blunder / missed_mate, either side


class StoredLine(BaseModel):
    rank: int
    eval: str
    win_pct: float  # White's win%, 0..100
    moves_uci: list[str]
    moves_san: list[str]


class StoredEngineResult(BaseModel):
    """The best stored search of one position (deep > verify > scan)."""

    fen: str
    tier: Tier
    depth: int
    lines: list[StoredLine]


class StoredSynopsis(BaseModel):
    text: str
    invalid_moves_removed: list[str]


MomentState = Literal["new", "intro", "attempt", "solved", "revealed"]


class MomentTry(BaseModel):
    uci: str
    san: str
    grade: str  # best / good / inaccuracy / mistake / blunder


class MomentMessage(BaseModel):
    role: Literal["coach", "player"]
    text: str
    kind: str


class MomentInfo(BaseModel):
    """A critical moment and the player's progress on it (SPEC_V2 §8.2). The engine's best move
    appears only once the moment is solved or revealed."""

    index: int
    ply: int
    move_number: int
    side: Literal["white", "black"]
    san: str
    uci: str
    label: MoveLabel
    eval_before: str
    eval_after: str
    state: MomentState  # "new" until the player opens it
    attempts: list[MomentTry]
    messages: list[MomentMessage]
    best_san: str | None = None
    best_uci: str | None = None


class GameDetail(BaseModel):
    """Everything the analysis board needs (SPEC_V2 §5.1): nothing is re-analyzed on open."""

    id: str
    status: GameStatus
    user_color: Color
    elo: int  # the player's Elo when the game was analyzed
    played_at: datetime
    info: GameInfo
    moves: list[MoveInfo]
    start_win_pct: float | None  # White's win% in the starting position
    final_fen: str
    final_is_terminal: bool
    accuracy: Accuracy | None
    counts: Counts | None
    engine_results: list[StoredEngineResult]
    # While status is "scanned", the positions still to verify, so the analysis can resume.
    verify_fens: list[str]
    synopsis: StoredSynopsis | None
    chat: list[ChatEntry]
    moments: list[MomentInfo] = []
