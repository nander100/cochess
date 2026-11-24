"""Verified payment events applied to players (SPEC_V4 §6.2). The only path, besides metered
usage and audited owner actions, by which a balance changes.

Each event is stored once in `billing_events` (a repeat is acknowledged and ignored), and its
effect goes through the ledger, whose (kind, source) uniqueness makes it safe to apply twice
anyway. Everything happens in the caller's transaction.
"""

import logging
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.ledger import (
    expire_due_allowance,
    grant_top_up,
    refund_credits,
    start_allowance,
)
from app.billing.provider import BillingEvent
from app.config import Settings
from app.db.models import BillingEventRow, User

logger = logging.getLogger("app.billing")

Outcome = Literal["applied", "ignored", "unmatched", "failed", "duplicate"]

ENDED_STATUSES = frozenset({"canceled", "incomplete_expired", "unpaid"})


def apply_event(
    session: Session, event: BillingEvent, settings: Settings, now: datetime
) -> Outcome:
    """Record `event` and apply it. "duplicate" when it was seen before (nothing changes)."""
    user = _find_user(session, event)
    row = BillingEventRow(
        provider=event.provider,
        event_id=event.event_id,
        type=event.type,
        user_id=user.id if user else None,
        amount_cents=event.amount_cents,
        currency=event.currency,
        outcome="ignored",
        received_at=now,
    )
    try:
        with session.begin_nested():
            session.add(row)
    except IntegrityError:
        return "duplicate"
    outcome = _apply(session, event, user, settings, now)
    row.outcome = outcome
    session.flush()
    # Ids only: never an email, a name or the provider's payload.
    logger.info("billing event %s %s (%s): %s", event.provider, event.event_id, event.type, outcome)
    return outcome


def _apply(
    session: Session, event: BillingEvent, user: User | None, settings: Settings, now: datetime
) -> Outcome:
    if event.kind == "other":
        return "ignored"
    if user is None:
        logger.warning("billing event %s names no player", event.event_id)
        return "unmatched"
    _remember_customer(user, event)
    match event.kind:
        case "top_up_paid":
            return _top_up(session, event, user, settings, now)
        case "period_paid":
            return _period(session, event, user, settings, now)
        case "subscription_changed":
            user.subscription_status = event.status
            user.subscription_period_end = event.period_end or user.subscription_period_end
            if event.status in ENDED_STATUSES:
                expire_due_allowance(session, user, now, everything=True)
            return "applied"
        case "subscription_ended":
            user.subscription_status = "canceled"
            expire_due_allowance(session, user, now, everything=True)
            return "applied"
        case "refund":
            return _refund(session, event, user, settings, now)
    return "ignored"


def _top_up(
    session: Session, event: BillingEvent, user: User, settings: Settings, now: datetime
) -> Outcome:
    product = settings.stripe.products.get(event.product or "")
    if product is None or product.recurring or not event.object_id:
        logger.error("top-up event %s has no one-time product", event.event_id)
        return "failed"
    amount = product.credits * settings.credits.microusd_per_credit
    grant_top_up(session, user, amount, f"{event.provider}:{event.object_id}", now)
    return "applied"


def _period(
    session: Session, event: BillingEvent, user: User, settings: Settings, now: datetime
) -> Outcome:
    product = settings.stripe.products.get(event.product or "")
    if product is None or event.period_end is None or not event.object_id:
        logger.error("period event %s has no product or period end", event.event_id)
        return "failed"
    amount = product.credits * settings.credits.microusd_per_credit
    source = f"{event.provider}:{event.object_id}"
    start_allowance(session, user, amount, source, event.period_end, now)
    if user.subscription_status is None or user.subscription_status in ENDED_STATUSES:
        user.subscription_status = "active"  # the subscription event may arrive after this one
    if user.subscription_period_end is None or user.subscription_period_end < event.period_end:
        user.subscription_period_end = event.period_end
    return "applied"


def _refund(
    session: Session, event: BillingEvent, user: User, settings: Settings, now: datetime
) -> Outcome:
    product = settings.stripe.products.get(event.product or "")
    if product is None or event.refund_fraction is None or not event.object_id:
        logger.error("refund event %s has no product or amount", event.event_id)
        return "failed"
    full = product.credits * settings.credits.microusd_per_credit
    refunded = round(full * min(max(event.refund_fraction, 0.0), 1.0))
    payment = f"{event.provider}:{event.object_id}"
    refund_credits(session, user, payment, refunded, event.event_id, now)
    return "applied"


def _find_user(session: Session, event: BillingEvent) -> User | None:
    """Our id from the event's metadata, checked against the provider's customer when both are
    known; otherwise the player whose customer this is."""
    by_customer = None
    if event.customer_id:
        by_customer = session.scalars(
            select(User).where(User.billing_customer_id == event.customer_id)
        ).first()
    if event.user_id:
        named = session.get(User, event.user_id)
        if named is not None and (by_customer is None or by_customer.id == named.id):
            return named
        if named is not None:
            logger.warning("billing event %s: metadata and customer disagree", event.event_id)
    return by_customer


def _remember_customer(user: User, event: BillingEvent) -> None:
    if event.customer_id and user.billing_customer_id is None:
        user.billing_customer_id = event.customer_id
        user.billing_provider = event.provider
