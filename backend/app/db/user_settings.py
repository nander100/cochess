"""Reading a player's settings outside the settings routes (SPEC_V3 §4.3, §9.3)."""

from typing import cast

from sqlalchemy.orm import Session

from app.coach.payload import DETAIL_FOR_BAND, DetailLevel, rating_band
from app.db.models import User, UserSettingsRow


def detail_level_for(session: Session, user_id: str | None) -> DetailLevel | None:
    """The player's chosen coach detail level, or None for "auto" (follow the rating band)."""
    row = session.get(UserSettingsRow, user_id) if user_id is not None else None
    return cast(DetailLevel | None, row.coach_detail_level) if row is not None else None


def usernames_for(session: Session, user_id: str) -> list[str]:
    """The player's Chess.com and Lichess usernames, for detecting their color in a PGN."""
    row = session.get(UserSettingsRow, user_id)
    if row is None:
        return []
    return [name for name in (row.chesscom_username, row.lichess_username) if name]


def effective_detail_level(session: Session, user_id: str | None) -> DetailLevel:
    """The level the coach writes at: the player's choice, else their rating band's default."""
    chosen = detail_level_for(session, user_id)
    if chosen is not None:
        return chosen
    user = session.get(User, user_id) if user_id is not None else None
    return DETAIL_FOR_BAND[rating_band(user.elo)] if user and user.elo is not None else "standard"
