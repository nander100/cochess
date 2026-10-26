"""`get_current_user`: the one dependency the rest of the app uses to know who is asking."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session
from app.auth.service import session_user
from app.config import Settings
from app.db.models import User

NOT_LOGGED_IN = "You're not logged in. Ask the owner for a new login link."


def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> User:
    token = request.cookies.get(settings.auth.cookie_name)
    user = session_user(session, token, datetime.now(UTC)) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOT_LOGGED_IN)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
