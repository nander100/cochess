"""The player's tendencies (SPEC_V2 §9, §11): GET /api/tendencies."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analysis.tendencies import TendencyReport, aggregate
from app.api.deps import get_app_settings, get_session
from app.auth.deps import CurrentUser
from app.config import Settings
from app.db.tendencies import latest_tendencies

router = APIRouter(prefix="/api/tendencies", tags=["tendencies"])


@router.get("")
def get_tendencies(
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> TendencyReport:
    """The latest snapshot (refreshed after every analyzed game); empty before the first one."""
    return latest_tendencies(session, user.id) or aggregate([], settings.tendencies)
