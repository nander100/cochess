"""Owner actions with their audit log (SPEC_V4 §10.2, §10.3). The dashboard and the CLI both go
through here, so every action writes exactly one `admin_actions` row in the caller's transaction
(nothing is committed here). `admin` is the owner who acted, or None from the server's CLI."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.auth import accounts
from app.billing.ledger import adjust_by_owner
from app.config import CreditSettings
from app.db.models import AdminActionRow, User

MAX_CREDITS = 10_000  # one change; a typo shouldn't hand out a fortune
MAX_NOTE = 200
MAX_REASON = 500


class ActionError(ValueError):
    """The action doesn't apply to this player (wrong status, bad amount, missing note)."""


def accept(
    session: Session, admin: User | None, user: User, now: datetime, credits: CreditSettings
) -> AdminActionRow:
    _account(lambda: accounts.admit(session, user, now, credits))
    return _record(session, admin, user, "accept", {}, now)


def suspend(
    session: Session,
    admin: User | None,
    user: User,
    now: datetime,
    *,
    reason: str,
    tell_reason: bool = False,
    cancelled_subscription: bool = False,
) -> AdminActionRow:
    """Revoke access (SPEC_V4 §4.4). Cancelling a subscription is the caller's job, done first and
    only when the owner chose it; this records whether it happened."""
    reason = reason.strip()
    if not reason:
        raise ActionError("revoking access needs a reason")
    if len(reason) > MAX_REASON:
        raise ActionError(f"the reason is longer than {MAX_REASON} characters")
    _account(lambda: accounts.suspend(session, user, now, reason=reason, tell_reason=tell_reason))
    details = {
        "reason": reason,
        "told_reason": tell_reason,
        "cancelled_subscription": cancelled_subscription,
    }
    return _record(session, admin, user, "suspend", details, now)


def restore(session: Session, admin: User | None, user: User, now: datetime) -> AdminActionRow:
    _account(lambda: accounts.restore(session, user, now))
    return _record(session, admin, user, "restore", {"status": user.status}, now)


def change_credits(
    session: Session,
    admin: User | None,
    user: User,
    credits: float,
    *,
    note: str,
    now: datetime,
    settings: CreditSettings,
) -> AdminActionRow:
    """Add (positive) or remove (negative) lasting credits; the ledger entry names this action."""
    note = note.strip()
    if not note:
        raise ActionError("adding or removing credits needs a note")
    if len(note) > MAX_NOTE:
        raise ActionError(f"the note is longer than {MAX_NOTE} characters")
    if credits == 0 or abs(credits) > MAX_CREDITS:
        raise ActionError(f"credits must be non-zero and at most {MAX_CREDITS:,} either way")
    microusd = round(credits * settings.microusd_per_credit)
    action = _record(session, admin, user, "credits", {"credits": credits, "note": note}, now)
    source = f"admin_action:{action.id}"
    adjust_by_owner(session, user, microusd, note=note, now=now, source=source)
    return action


def set_metering(
    session: Session, admin: User | None, user: User, *, unmetered: bool, now: datetime
) -> AdminActionRow:
    if user.unmetered == unmetered:
        state = "unmetered" if unmetered else "metered"
        raise ActionError(f'"{user.name}" is already {state}')
    user.unmetered = unmetered
    return _record(session, admin, user, "metering", {"unmetered": unmetered}, now)


def set_role(
    session: Session, admin: User | None, user: User, role: str, now: datetime
) -> AdminActionRow:
    """CLI only: the role is never set from the web app (SPEC_V4 §10)."""
    before = user.role
    _account(lambda: accounts.set_role(user, role))
    return _record(session, admin, user, "set_role", {"from": before, "to": role}, now)


def _account(change: Callable[[], None]) -> None:
    try:
        change()
    except accounts.AccountError as error:
        raise ActionError(str(error)) from error


def _record(
    session: Session,
    admin: User | None,
    user: User,
    action: str,
    details: dict[str, Any],
    now: datetime,
) -> AdminActionRow:
    row = AdminActionRow(
        admin_user_id=admin.id if admin else None,
        target_user_id=user.id,
        action=action,
        details=details,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row
