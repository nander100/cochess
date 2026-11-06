"""Per-player settings (SPEC_V3 §4.3): GET / PATCH /api/settings."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.auth.deps import CurrentUser
from app.coach.payload import DETAIL_FOR_BAND, DetailLevel, rating_band
from app.db.models import User, UserSettingsRow

router = APIRouter(prefix="/api/settings", tags=["settings"])

ThemeName = Literal["light", "dark", "system"]
BoardScheme = Literal["blue", "pale", "soft"]
PieceSet = Literal["cburnett", "merida"]
# "auto": the level follows the player's rating band (SPEC_V3 §9.3, PLAN_V3 adjustment 5).
DetailChoice = Literal["auto", "plain", "standard", "technical"]
DEFAULT_DETAIL: DetailLevel = "standard"  # for a player who hasn't given a rating yet
Seconds = Annotated[float, Field(ge=0.75, le=3)]
# Chess.com and Lichess usernames: letters, digits, "_" and "-". Empty clears it.
Username = Annotated[str, Field(max_length=50, pattern=r"^[A-Za-z0-9_-]*$")]


class UserSettings(BaseModel):
    theme: ThemeName = "light"  # the design's default (docs/design/screens.md)
    board_scheme: BoardScheme = "blue"
    piece_set: PieceSet = "cburnett"
    sounds: bool = False
    engine_panel: bool = False
    coach_detail_level: DetailChoice = "auto"
    playback_seconds: Seconds = 1.5  # one move every this many seconds (§9.5)
    chesscom_username: Username = ""
    lichess_username: Username = ""


class SettingsResponse(UserSettings):
    # What "auto" means for this player now: how the coach writes and how moves are shown.
    effective_detail_level: DetailLevel


class SettingsUpdate(BaseModel):
    """Only the fields sent are changed."""

    theme: ThemeName | None = None
    board_scheme: BoardScheme | None = None
    piece_set: PieceSet | None = None
    sounds: bool | None = None
    engine_panel: bool | None = None
    coach_detail_level: DetailChoice | None = None
    playback_seconds: Seconds | None = None
    chesscom_username: Username | None = None
    lichess_username: Username | None = None


SessionDep = Annotated[Session, Depends(get_session)]


def _of(row: UserSettingsRow | None) -> UserSettings:
    if row is None:
        return UserSettings()
    return UserSettings(
        theme=cast(ThemeName, row.theme),  # validated on write
        board_scheme=cast(BoardScheme, row.board_scheme),
        piece_set=cast(PieceSet, row.piece_set),
        sounds=row.sounds,
        engine_panel=row.engine_panel,
        coach_detail_level=cast(DetailChoice, row.coach_detail_level or "auto"),
        playback_seconds=row.playback_seconds,
        chesscom_username=row.chesscom_username or "",
        lichess_username=row.lichess_username or "",
    )


def _response(settings: UserSettings, user: User) -> SettingsResponse:
    choice = settings.coach_detail_level
    if choice != "auto":
        effective: DetailLevel = choice
    elif user.elo is not None:
        effective = DETAIL_FOR_BAND[rating_band(user.elo)]
    else:
        effective = DEFAULT_DETAIL
    return SettingsResponse(**settings.model_dump(), effective_detail_level=effective)


def _columns(settings: UserSettings) -> dict[str, object]:
    values = settings.model_dump()
    values["coach_detail_level"] = (
        None if settings.coach_detail_level == "auto" else settings.coach_detail_level
    )
    for field in ("chesscom_username", "lichess_username"):
        values[field] = values[field].strip() or None
    return values


@router.get("")
def read_settings(user: CurrentUser, session: SessionDep) -> SettingsResponse:
    return _response(_of(session.get(UserSettingsRow, user.id)), user)


@router.patch("")
def update_settings(
    body: SettingsUpdate, user: CurrentUser, session: SessionDep
) -> SettingsResponse:
    row = session.get(UserSettingsRow, user.id)
    merged = _of(row).model_copy(update=body.model_dump(exclude_none=True))
    if row is None:
        row = UserSettingsRow(user_id=user.id, **_columns(merged))
        session.add(row)
    else:
        for field, value in _columns(merged).items():
            setattr(row, field, value)
    session.commit()
    return _response(_of(row), user)
