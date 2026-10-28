"""The optional per-player daily token limit (SPEC_V2 §12, `USER_DAILY_TOKEN_LIMIT`)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session
from app.auth.deps import CurrentUser
from app.config import Settings
from app.db.coach import tokens_used_since

OVER_LIMIT = (
    "You've used today's coaching allowance while CoChess is in testing. Please come back tomorrow."
)


def check_token_budget(
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> None:
    """Refuse a coach call (429) once the player's tokens in the last 24 hours reach the limit.
    Off when no limit is set."""
    limit = settings.user_daily_token_limit
    if limit is None:
        return
    since = datetime.now(UTC) - timedelta(days=1)
    if tokens_used_since(session, user.id, since) >= limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=OVER_LIMIT)
