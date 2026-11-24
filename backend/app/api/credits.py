"""Coaching credits on the API (SPEC_V4 §5, §7): the check before every coach call, the player's
coach strength for the call, and GET /api/billing for the credits UI."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session
from app.auth.deps import CurrentUser
from app.billing.ledger import balance, history
from app.config import CoachTier, Settings
from app.db.models import CreditLedgerRow, LlmUsageRow, UserSettingsRow

router = APIRouter(prefix="/api/billing", tags=["billing"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

OUT_OF_CREDITS = (
    "You're out of coaching credits. Analysis and everything else still work; top up or "
    "subscribe to keep getting coached."
)
DAILY_CAP = "You've reached today's coaching limit. It resets within 24 hours."


def require_credit(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> None:
    """Before a coach call (SPEC_V4 §5.3): a positive balance, and under the daily spending cap.
    Unmetered players (the owner, testers) always pass; their usage is still priced."""
    if user.unmetered:
        return
    if balance(session, user.id).total <= 0:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail=OUT_OF_CREDITS)
    since = datetime.now(UTC) - timedelta(days=1)
    if spent_since(session, user.id, since) >= settings.credits.daily_cap_microusd:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=DAILY_CAP)


def coach_strength(session: Session, user_id: str) -> CoachTier:
    row = session.get(UserSettingsRow, user_id)
    return "deep" if row is not None and row.coach_strength == "deep" else "standard"


def get_coach_settings(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> Settings:
    """The app's settings with this player's coach strength, so each coach task picks its model
    by tier (`Settings.coach_model`) and its usage is recorded with the tier."""
    return settings.model_copy(update={"coach_tier": coach_strength(session, user.id)})


CoachSettingsDep = Annotated[Settings, Depends(get_coach_settings)]


def spent_since(session: Session, user_id: str, since: datetime) -> int:
    query = select(func.coalesce(func.sum(LlmUsageRow.cost_microusd), 0)).where(
        LlmUsageRow.user_id == user_id, LlmUsageRow.created_at >= since
    )
    return int(session.scalar(query) or 0)


class LedgerEntry(BaseModel):
    kind: str
    credits: float
    note: str | None
    created_at: datetime


class Billing(BaseModel):
    credits: float
    allowance_credits: float
    unmetered: bool
    # Under the warning share of the last allowance (or the trial), and at or below zero.
    low: bool
    out: bool
    coach_strength: CoachTier
    credits_per_game: dict[str, float]
    history: list[LedgerEntry]


@router.get("")
def read_billing(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> Billing:
    per_credit = settings.credits.microusd_per_credit
    now = balance(session, user.id)
    reference = _last_top_up(session, user.id) or settings.credits.trial_credits * per_credit
    return Billing(
        credits=round(now.total / per_credit, 2),
        allowance_credits=round(max(now.allowance, 0) / per_credit, 2),
        unmetered=user.unmetered,
        low=not user.unmetered and now.total < settings.credits.warn_fraction * reference,
        out=not user.unmetered and now.total <= 0,
        coach_strength=coach_strength(session, user.id),
        credits_per_game=settings.credits.credits_per_game,
        history=[
            LedgerEntry(
                kind=entry.kind,
                credits=round(entry.delta_microusd / per_credit, 2),
                note=entry.note,
                created_at=entry.created_at,
            )
            for entry in history(session, user.id)
        ],
    )


def _last_top_up(session: Session, user_id: str) -> int | None:
    """The latest allowance, top-up or trial: what "running low" is measured against."""
    query = (
        select(CreditLedgerRow.delta_microusd)
        .where(
            CreditLedgerRow.user_id == user_id,
            CreditLedgerRow.kind.in_(("allowance", "trial", "top_up")),
        )
        .order_by(CreditLedgerRow.created_at.desc(), CreditLedgerRow.id.desc())
        .limit(1)
    )
    return cast(int | None, session.scalar(query))
