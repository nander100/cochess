"""Email preferences (SPEC_V4 §12.4): a player turns the optional emails on or off from their
profile, or with the one-click link in each one (signed, no login; also mail apps' own button,
RFC 8058). The other account emails can't be turned off."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session
from app.auth.deps import CurrentAccount
from app.config import Settings
from app.db.models import User
from app.email.preferences import preferences, read_token, set_group

router = APIRouter(tags=["email"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

BAD_LINK = "This link isn't valid. You can turn emails off from your profile instead."


class EmailPreferences(BaseModel):
    preferences: dict[str, bool]


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credits_balance: bool | None = None
    credits_added: bool | None = None


class Unsubscribed(BaseModel):
    group: str


@router.get("/api/me/email")
def read_preferences(user: CurrentAccount, session: SessionDep) -> EmailPreferences:
    return EmailPreferences(preferences=preferences(session, user.id))


@router.patch("/api/me/email")
def update_preferences(
    body: PreferencesUpdate, user: CurrentAccount, session: SessionDep
) -> EmailPreferences:
    now = datetime.now(UTC)
    for group, enabled in body.model_dump(exclude_none=True).items():
        set_group(session, user.id, group, enabled, now)
    session.commit()
    return EmailPreferences(preferences=preferences(session, user.id))


@router.post("/api/email/unsubscribe")
def unsubscribe(token: str, session: SessionDep, settings: SettingsDep) -> Unsubscribed:
    """Turn off the group the link was for. A deleted account's link quietly does nothing."""
    found = read_token(settings.email, token)
    if found is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=BAD_LINK)
    user_id, group = found
    if session.get(User, user_id) is not None:
        set_group(session, user_id, group, False, datetime.now(UTC))
        session.commit()
    return Unsubscribed(group=group)
