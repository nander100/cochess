"""A player's own account (SPEC_V4 §11): export everything that's theirs. Any signed-in account
may use it, including a waitlisted or paused one."""

import math
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.account.export import build_export
from app.api.deps import get_app_settings, get_session
from app.auth.deps import CurrentAccount
from app.config import Settings

router = APIRouter(prefix="/api/me", tags=["account"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@router.post("/export")
def export(
    request: Request, user: CurrentAccount, session: SessionDep, settings: SettingsDep
) -> Response:
    """Everything that's the player's, as one zip download."""
    _check_cooldown(request, user.id, settings.limits.export_cooldown_seconds)
    now = datetime.now(UTC)
    data = build_export(session, user, settings, now)
    filename = f"cochess-export-{now:%Y-%m-%d}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _check_cooldown(request: Request, user_id: str, cooldown: float) -> None:
    times: dict[str, float] = request.app.state.export_times
    now = time.monotonic()
    wait = cooldown - (now - times.get(user_id, -math.inf))
    if wait > 0:
        minutes = max(1, math.ceil(wait / 60))
        detail = f"You just exported your data. Try again in {minutes} minutes."
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)
    times[user_id] = now
