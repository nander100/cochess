"""Reading a player's settings outside the settings routes (SPEC_V3 §4.3, §9.3)."""

from typing import cast

from sqlalchemy.orm import Session

from app.coach.payload import DetailLevel
from app.db.models import UserSettingsRow


def detail_level_for(session: Session, user_id: str | None) -> DetailLevel | None:
    """The player's chosen coach detail level, or None for "auto" (follow the rating band)."""
    row = session.get(UserSettingsRow, user_id) if user_id is not None else None
    return cast(DetailLevel | None, row.coach_detail_level) if row is not None else None
