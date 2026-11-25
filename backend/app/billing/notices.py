"""Running low and running out (SPEC_V4 §5.3, §12.4). "Low" is under the warning share of the
latest grant (an allowance, a top-up, or the trial before either); each email goes at most once
per such grant, which is at most once per billing period."""

from datetime import datetime
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.ledger import balance
from app.config import Settings
from app.db.models import CreditLedgerRow, User
from app.email.outbox import queue_email

GRANTS = ("allowance", "trial", "top_up")


class Grant(NamedTuple):
    id: int | None  # None before any grant
    microusd: int


def last_grant(session: Session, user_id: str, settings: Settings) -> Grant:
    """The latest allowance, top-up or trial: what "running low" is measured against."""
    query = (
        select(CreditLedgerRow.id, CreditLedgerRow.delta_microusd)
        .where(CreditLedgerRow.user_id == user_id, CreditLedgerRow.kind.in_(GRANTS))
        .order_by(CreditLedgerRow.created_at.desc(), CreditLedgerRow.id.desc())
        .limit(1)
    )
    found = session.execute(query).first()
    if found is None:
        trial = settings.credits.trial_credits * settings.credits.microusd_per_credit
        return Grant(None, trial)
    return Grant(int(found[0]), int(found[1]))


def notify_balance(session: Session, user: User, settings: Settings, now: datetime) -> None:
    """After a charge: queue credits_out at zero or below, else credits_low under the warning
    share (in the caller's transaction). Never for a player who isn't charged."""
    if user.unmetered:
        return
    total = balance(session, user.id).total
    grant = last_grant(session, user.id, settings)
    anchor = grant.id if grant.id is not None else "start"
    if total <= 0:
        kind = "credits_out"
    elif total < settings.credits.warn_fraction * grant.microusd:
        kind = "credits_low"
    else:
        return
    queue_email(session, user, kind, f"{kind}:{user.id}:{anchor}", now=now)
