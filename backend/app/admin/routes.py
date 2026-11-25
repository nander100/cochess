"""The owner dashboard's API (SPEC_V4 §10, §14.1). Every route answers 404 to anyone who isn't a
signed-in, active owner, including someone not signed in at all, so the routes don't show that
they exist. Every action is confirmed in the UI and written to the audit log here."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import actions
from app.admin.overview import Overview, Period, overview
from app.admin.users import (
    Plan,
    Sort,
    Status,
    Strength,
    UserDetail,
    UserFilters,
    UserPage,
    list_users,
    user_detail,
)
from app.api.deps import get_app_settings, get_session
from app.auth.deps import get_current_account
from app.billing.provider import BillingProvider
from app.config import Settings
from app.db.models import User

logger = logging.getLogger("app.admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

NOT_FOUND = "Not found"
NO_PLAYER = "No such player."
PAYMENTS_OFF = "Payments aren't set up, so the subscription can't be cancelled from here."
PROVIDER_FAILED = "Stripe didn't cancel the subscription, so nothing was changed. Try again."
SELF = "You can't revoke your own access."
LIVE = frozenset({"active", "trialing", "past_due", "incomplete"})
MAX_BULK = 100


def require_owner(request: Request, session: SessionDep, settings: SettingsDep) -> User:
    try:
        user = get_current_account(request, session, settings)
    except HTTPException as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND) from error
    if user.role != "owner" or user.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return user


Owner = Annotated[User, Depends(require_owner)]


class SuspendRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=actions.MAX_REASON)
    tell_reason: bool = False
    cancel_subscription: bool = False


class CreditsRequest(BaseModel):
    credits: float
    note: str = Field(min_length=1, max_length=actions.MAX_NOTE)


class MeteringRequest(BaseModel):
    unmetered: bool


class BulkAcceptRequest(BaseModel):
    user_ids: list[str] = Field(min_length=1, max_length=MAX_BULK)


class BulkAccepted(BaseModel):
    accepted: int
    skipped: list[str]  # names (or ids) no longer on the waitlist


@router.get("/overview")
def read_overview(owner: Owner, session: SessionDep, period: Period = "30d") -> Overview:
    return overview(session, period, datetime.now(UTC))


@router.get("/users")
def read_users(
    owner: Owner,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[Status | None, Query(alias="status")] = None,
    plan: Plan | None = None,
    strength: Strength | None = None,
    zero_credits: bool = False,
    sort: Sort = "-joined",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> UserPage:
    filters = UserFilters(
        q=q,
        status=status_,
        plan=plan,
        strength=strength,
        zero_credits=zero_credits,
        sort=sort,
        page=page,
    )
    return list_users(session, filters, datetime.now(UTC))


@router.get("/users/{user_id}")
def read_user(user_id: str, owner: Owner, session: SessionDep, settings: SettingsDep) -> UserDetail:
    return _detail(session, settings, user_id)


@router.post("/users/accept")
def accept_many(
    body: BulkAcceptRequest, owner: Owner, session: SessionDep, settings: SettingsDep
) -> BulkAccepted:
    """Accept a selection from the waitlist, one audited action each. Anyone no longer waiting
    (accepted meanwhile, or not found) is skipped and named."""
    now = datetime.now(UTC)
    ids = list(dict.fromkeys(body.user_ids))
    found = {u.id: u for u in session.scalars(select(User).where(User.id.in_(ids)))}
    accepted, skipped = 0, []
    for user_id in ids:
        user = found.get(user_id)
        if user is None or user.status != "waitlisted":
            skipped.append(user.name if user else user_id)
            continue
        actions.accept(session, owner, user, now, settings.credits)
        accepted += 1
    session.commit()
    return BulkAccepted(accepted=accepted, skipped=skipped)


@router.post("/users/{user_id}/accept")
def accept_one(
    user_id: str, owner: Owner, session: SessionDep, settings: SettingsDep
) -> UserDetail:
    user = _target(session, user_id)
    now = datetime.now(UTC)
    _act(session, lambda: actions.accept(session, owner, user, now, settings.credits))
    return _detail(session, settings, user_id)


@router.post("/users/{user_id}/suspend")
def suspend(
    user_id: str,
    body: SuspendRequest,
    request: Request,
    owner: Owner,
    session: SessionDep,
    settings: SettingsDep,
) -> UserDetail:
    """Revoke access. A live subscription is cancelled only when the owner ticked it, and first:
    if Stripe refuses, nothing changes (SPEC_V4 §10.2: never cancelled silently)."""
    user = _target(session, user_id)
    if user.id == owner.id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=SELF)
    if not body.reason.strip():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="revoking access needs a reason")
    cancelled = False
    if body.cancel_subscription and user.subscription_status in LIVE and user.billing_customer_id:
        _cancel_subscription(request, user)
        cancelled = True
    now = datetime.now(UTC)

    def revoke() -> object:
        return actions.suspend(
            session,
            owner,
            user,
            now,
            reason=body.reason,
            tell_reason=body.tell_reason,
            cancelled_subscription=cancelled,
        )

    _act(session, revoke)
    return _detail(session, settings, user_id)


@router.post("/users/{user_id}/restore")
def restore(user_id: str, owner: Owner, session: SessionDep, settings: SettingsDep) -> UserDetail:
    user = _target(session, user_id)
    now = datetime.now(UTC)
    _act(session, lambda: actions.restore(session, owner, user, now))
    return _detail(session, settings, user_id)


@router.post("/users/{user_id}/credits")
def change_credits(
    user_id: str, body: CreditsRequest, owner: Owner, session: SessionDep, settings: SettingsDep
) -> UserDetail:
    user = _target(session, user_id)
    now = datetime.now(UTC)

    def change() -> object:
        return actions.change_credits(
            session, owner, user, body.credits, note=body.note, now=now, settings=settings.credits
        )

    _act(session, change)
    return _detail(session, settings, user_id)


@router.post("/users/{user_id}/metering")
def set_metering(
    user_id: str, body: MeteringRequest, owner: Owner, session: SessionDep, settings: SettingsDep
) -> UserDetail:
    user = _target(session, user_id)
    now = datetime.now(UTC)
    _act(
        session,
        lambda: actions.set_metering(session, owner, user, unmetered=body.unmetered, now=now),
    )
    return _detail(session, settings, user_id)


def _cancel_subscription(request: Request, user: User) -> None:
    provider = cast(BillingProvider | None, request.app.state.billing_provider)
    if provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=PAYMENTS_OFF)
    try:
        provider.cancel_subscriptions(cast(str, user.billing_customer_id))
    except Exception as error:  # any provider failure: change nothing, tell the owner
        logger.warning(
            "cancelling a subscription failed for user %s: %s", user.id, type(error).__name__
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=PROVIDER_FAILED) from error


def _target(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None or user.status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_PLAYER)
    return user


def _act(session: Session, action: Callable[[], object]) -> None:
    """Run an owner action and commit it with its audit row, or roll back and say why."""
    try:
        action()
    except actions.ActionError as error:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    session.commit()


def _detail(session: Session, settings: Settings, user_id: str) -> UserDetail:
    detail = user_detail(session, user_id, datetime.now(UTC))
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_PLAYER)
    customer = detail.billing_customer_id
    if customer:
        test = (settings.stripe.secret_key or "").startswith(("sk_test_", "rk_test_"))
        base = "https://dashboard.stripe.com/test" if test else "https://dashboard.stripe.com"
        detail.billing_dashboard_url = f"{base}/customers/{customer}"
    return detail
