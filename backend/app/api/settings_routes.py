"""Per-player settings (SPEC_V3 §4.3): GET / PATCH /api/settings."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.auth.deps import CurrentUser
from app.db.models import UserSettingsRow

router = APIRouter(prefix="/api/settings", tags=["settings"])

ThemeName = Literal["light", "dark", "system"]
BoardScheme = Literal["blue", "pale", "soft"]
PieceSet = Literal["cburnett", "merida"]


class UserSettings(BaseModel):
    theme: ThemeName = "light"  # the design's default (docs/design/screens.md)
    board_scheme: BoardScheme = "blue"
    piece_set: PieceSet = "cburnett"
    sounds: bool = False
    engine_panel: bool = False


class SettingsUpdate(BaseModel):
    """Only the fields sent are changed."""

    theme: ThemeName | None = None
    board_scheme: BoardScheme | None = None
    piece_set: PieceSet | None = None
    sounds: bool | None = None
    engine_panel: bool | None = None


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
    )


@router.get("")
def read_settings(user: CurrentUser, session: SessionDep) -> UserSettings:
    return _of(session.get(UserSettingsRow, user.id))


@router.patch("")
def update_settings(body: SettingsUpdate, user: CurrentUser, session: SessionDep) -> UserSettings:
    row = session.get(UserSettingsRow, user.id)
    merged = _of(row).model_copy(update=body.model_dump(exclude_none=True))
    if row is None:
        row = UserSettingsRow(user_id=user.id, **merged.model_dump())
        session.add(row)
    else:
        for field, value in merged.model_dump().items():
            setattr(row, field, value)
    session.commit()
    return _of(row)
