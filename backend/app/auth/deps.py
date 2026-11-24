"""Who is asking (SPEC_V4 §4): `CurrentUser` is an active player, which every data route needs;
`CurrentAccount` is any signed-in account, for the few routes a waitlisted or paused player may
use (their status, sign-out, and later export and deletion)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session
from app.auth.service import session_user
from app.config import Settings
from app.db.models import User

NOT_LOGGED_IN = "You're not logged in. Sign in with Google, or ask the owner for a login link."
WAITING = "Your account is waiting for approval. We'll email you as soon as it's ready."
PAUSED = "Your access has been paused. You can still download or delete your data."
_ACTIVE_EVERY = timedelta(hours=1)  # last_active_at is written at most this often


def get_current_account(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> User:
    token = request.cookies.get(settings.auth.cookie_name)
    now = datetime.now(UTC)
    user = session_user(session, token, now) if token else None
    if user is None or user.status == "deleted":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOT_LOGGED_IN)
    if user.last_active_at is None or now - user.last_active_at >= _ACTIVE_EVERY:
        user.last_active_at = now
        session.commit()
    return user


CurrentAccount = Annotated[User, Depends(get_current_account)]


def get_current_user(account: CurrentAccount) -> User:
    if account.status == "waitlisted":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=WAITING)
    if account.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=PAUSED)
    return account


CurrentUser = Annotated[User, Depends(get_current_user)]
