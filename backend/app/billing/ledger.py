"""The credit ledger (SPEC_V4 §5.2). Every change is a ledger row plus the same change to the
player's balance, in the caller's transaction (nothing is committed here). (kind, source) is
unique, so a replayed webhook, a retried charge or a second trial changes nothing.

The balance has two parts: the period's allowance, spent first and removed when it expires, and
lasting credit (trial, top-ups, owner grants). On Postgres the balance row is locked while it
changes, so simultaneous charges can't overwrite each other.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import CreditSettings
from app.db.models import CreditBalanceRow, CreditLedgerRow, User


@dataclass(frozen=True)
class Balance:
    allowance: int  # microdollars
    lasting: int

    @property
    def total(self) -> int:
        return self.allowance + self.lasting


def balance(session: Session, user_id: str) -> Balance:
    row = session.get(CreditBalanceRow, user_id)
    return Balance(0, 0) if row is None else Balance(row.allowance_microusd, row.lasting_microusd)


def history(session: Session, user_id: str, limit: int = 50) -> list[CreditLedgerRow]:
    """Newest first."""
    query = (
        select(CreditLedgerRow)
        .where(CreditLedgerRow.user_id == user_id)
        .order_by(CreditLedgerRow.created_at.desc(), CreditLedgerRow.id.desc())
        .limit(limit)
    )
    return list(session.scalars(query))


def grant_trial(session: Session, user: User, now: datetime, credits: CreditSettings) -> None:
    """The free trial, once per player however often it's asked for (SPEC_V4 §6.1)."""
    amount = credits.trial_credits * credits.microusd_per_credit
    _record(session, user.id, amount, "trial", f"trial:{user.id}", "lasting", now)


def grant_allowance(
    session: Session, user: User, microusd: int, source: str, expires_at: datetime, now: datetime
) -> None:
    """A paid period's allowance (M4: from the subscription's paid invoice)."""
    _record(
        session, user.id, microusd, "allowance", source, "allowance", now, expires_at=expires_at
    )


def expire_allowance(session: Session, user: User, source: str, now: datetime) -> None:
    """Remove what's left of the allowance at the end of its period (once per period)."""
    if _exists(session, "expiry", f"expiry:{source}"):
        return
    remaining = max(_locked(session, user.id).allowance_microusd, 0)
    _record(session, user.id, -remaining, "expiry", f"expiry:{source}", "allowance", now)


def grant_top_up(session: Session, user: User, microusd: int, source: str, now: datetime) -> bool:
    """A paid one-time purchase: lasting credit. False when this payment was already counted."""
    return _record(session, user.id, microusd, "top_up", source, "lasting", now) is not None


def expire_due_allowance(
    session: Session, user: User, now: datetime, *, everything: bool = False
) -> None:
    """Expire every allowance whose period has ended (read lazily: before a credit check and
    when the balance is shown, so no scheduler is needed), or all of them (`everything`: the
    subscription ended)."""
    for source in _unexpired_allowances(session, user.id, before=None if everything else now):
        expire_allowance(session, user, source, now)


def start_allowance(
    session: Session, user: User, microusd: int, source: str, expires_at: datetime, now: datetime
) -> bool:
    """A newly paid period: what's left of earlier allowances goes, then this one is granted.
    A replay of the same period changes nothing (and never expires the current one)."""
    if _exists(session, "allowance", source):
        return False
    for earlier in _unexpired_allowances(session, user.id, before=None):
        expire_allowance(session, user, earlier, now)
    grant_allowance(session, user, microusd, source, expires_at, now)
    return True


def refund_credits(
    session: Session, user: User, payment: str, refunded_microusd: int, event: str, now: datetime
) -> int:
    """Take back credits for money refunded on `payment`. `refunded_microusd` is the credit value
    of everything refunded on it so far (providers report the running total), so a later partial
    refund only removes the difference. Allowance goes first; the balance may go below zero.
    Returns what was removed."""
    prefix = f"refund:{payment}:"
    query = select(func.coalesce(func.sum(CreditLedgerRow.delta_microusd), 0)).where(
        CreditLedgerRow.kind == "refund", CreditLedgerRow.source.startswith(prefix)
    )
    already = -int(session.scalar(query) or 0)
    owed = refunded_microusd - already
    source = prefix + event
    if owed <= 0 or _exists(session, "refund", source):
        return 0
    _debit(session, user.id, owed, "refund", source, now)
    return owed


def adjust_by_owner(
    session: Session,
    user: User,
    microusd: int,
    *,
    note: str,
    now: datetime,
    source: str | None = None,
) -> CreditLedgerRow:
    """Credits the owner adds or removes (dashboard or CLI), always with a note (SPEC_V4 §10).
    `source` names the owner action it came from (`admin_action:<id>`, SPEC_V4 §10.3)."""
    if not note.strip():
        raise ValueError("an owner grant or removal needs a note")
    kind = "owner_grant" if microusd >= 0 else "owner_removal"
    origin = source or f"owner:{uuid.uuid4()}"
    entry = _record(session, user.id, microusd, kind, origin, "lasting", now, note=note.strip())
    if entry is None:  # each action, like a fresh uuid, is recorded once
        raise RuntimeError("owner adjustment was not recorded")
    return entry


def charge_usage(
    session: Session, user_id: str, usage_row_id: int, cost_microusd: int, now: datetime
) -> None:
    """Charge one coach call: allowance first, then lasting credit, which may go below zero
    (the call already happened; the next one is refused until the balance is positive)."""
    source = f"llm_usage:{usage_row_id}"
    if _exists(session, "usage", source):
        return
    _debit(session, user_id, cost_microusd, "usage", source, now)


def _debit(
    session: Session, user_id: str, microusd: int, kind: str, source: str, now: datetime
) -> None:
    """Remove `microusd`: allowance first, then lasting credit (which may go below zero)."""
    row = _locked(session, user_id)
    from_allowance = min(microusd, max(row.allowance_microusd, 0))
    from_lasting = microusd - from_allowance
    bucket = "allowance" if from_lasting == 0 else "lasting" if from_allowance == 0 else "split"
    row.allowance_microusd -= from_allowance
    row.lasting_microusd -= from_lasting
    session.add(
        CreditLedgerRow(
            user_id=user_id,
            delta_microusd=-microusd,
            kind=kind,
            source=source,
            bucket=bucket,
            created_at=now,
        )
    )
    session.flush()


def _unexpired_allowances(session: Session, user_id: str, before: datetime | None) -> list[str]:
    """Sources of this player's allowances with no expiry yet (ending before `before`, if set)."""
    expired = select(CreditLedgerRow.source).where(
        CreditLedgerRow.user_id == user_id, CreditLedgerRow.kind == "expiry"
    )
    query = select(CreditLedgerRow.source).where(
        CreditLedgerRow.user_id == user_id,
        CreditLedgerRow.kind == "allowance",
        ("expiry:" + CreditLedgerRow.source).not_in(expired),
    )
    if before is not None:
        query = query.where(CreditLedgerRow.expires_at <= before)
    return list(session.scalars(query.order_by(CreditLedgerRow.id)))


def _record(
    session: Session,
    user_id: str,
    delta: int,
    kind: str,
    source: str,
    bucket: str,
    now: datetime,
    *,
    note: str | None = None,
    expires_at: datetime | None = None,
) -> CreditLedgerRow | None:
    """Add one entry and apply it to its bucket; a repeat (kind, source) is ignored."""
    if _exists(session, kind, source):
        return None
    row = _locked(session, user_id)
    if bucket == "allowance":
        row.allowance_microusd += delta
    else:
        row.lasting_microusd += delta
    entry = CreditLedgerRow(
        user_id=user_id,
        delta_microusd=delta,
        kind=kind,
        source=source,
        bucket=bucket,
        note=note,
        expires_at=expires_at,
        created_at=now,
    )
    session.add(entry)
    session.flush()
    return entry


def _exists(session: Session, kind: str, source: str) -> bool:
    query = select(CreditLedgerRow.id).where(
        CreditLedgerRow.kind == kind, CreditLedgerRow.source == source
    )
    return session.scalar(query) is not None


def _locked(session: Session, user_id: str) -> CreditBalanceRow:
    """The player's balance row, locked until the transaction ends (Postgres; SQLite ignores
    the lock and serializes writes itself). Made on first use."""
    query = select(CreditBalanceRow).where(CreditBalanceRow.user_id == user_id).with_for_update()
    row = session.scalars(query).first()
    if row is not None:
        return row
    try:
        with session.begin_nested():
            session.add(CreditBalanceRow(user_id=user_id, allowance_microusd=0, lasting_microusd=0))
    except IntegrityError:
        pass  # another transaction made it first
    found = session.scalars(query).first()
    if found is None:
        raise RuntimeError(f"no balance row for user {user_id}")
    return found
