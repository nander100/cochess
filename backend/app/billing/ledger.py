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

from sqlalchemy import select
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


def adjust_by_owner(
    session: Session, user: User, microusd: int, *, note: str, now: datetime
) -> CreditLedgerRow:
    """Credits the owner adds or removes (dashboard or CLI), always with a note (SPEC_V4 §10)."""
    if not note.strip():
        raise ValueError("an owner grant or removal needs a note")
    kind = "owner_grant" if microusd >= 0 else "owner_removal"
    entry = _record(
        session, user.id, microusd, kind, f"owner:{uuid.uuid4()}", "lasting", now, note=note.strip()
    )
    if entry is None:  # a fresh uuid can't repeat
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
    row = _locked(session, user_id)
    from_allowance = min(cost_microusd, max(row.allowance_microusd, 0))
    from_lasting = cost_microusd - from_allowance
    bucket = "allowance" if from_lasting == 0 else "lasting" if from_allowance == 0 else "split"
    row.allowance_microusd -= from_allowance
    row.lasting_microusd -= from_lasting
    session.add(
        CreditLedgerRow(
            user_id=user_id,
            delta_microusd=-cost_microusd,
            kind="usage",
            source=source,
            bucket=bucket,
            created_at=now,
        )
    )
    session.flush()


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
