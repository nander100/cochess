"""Owner actions on accounts (SPEC_V4 §4.3, §4.4): accept from the waitlist, pause and restore
access, set a role. Each one changes the account and queues its email in the caller's transaction
(nothing is committed here). Used by the CLI now and the owner dashboard in M5, which adds the
audit log."""

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.billing.ledger import grant_trial
from app.config import CreditSettings
from app.db.models import AuthSession, User
from app.email.outbox import queue_email

ROLES = ("player", "owner")


class AccountError(ValueError):
    pass


def admit(
    session: Session, user: User, now: datetime, credits: CreditSettings | None = None
) -> None:
    """Waitlisted to active, with the free trial and the acceptance email (each once per player,
    SPEC_V4 §4.3, §6.1)."""
    if user.status != "waitlisted":
        raise AccountError(f'"{user.name}" is not on the waitlist (status: {user.status})')
    user.status, user.admitted_at = "active", now
    grant_trial(session, user, now, credits or CreditSettings())
    queue_email(session, user, "accepted", f"accepted:{user.id}", now=now)


def suspend(
    session: Session, user: User, now: datetime, *, reason: str, tell_reason: bool = False
) -> None:
    """Pause access: the player is signed out everywhere at once. The reason stays with the owner
    (the audit log, from M5) unless `tell_reason` puts it in the email."""
    if user.status not in ("active", "waitlisted"):
        raise AccountError(f'"{user.name}" can\'t be paused (status: {user.status})')
    user.status = "suspended"
    session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    details = {"note": f" The reason given: {reason.strip()}"} if tell_reason and reason else {}
    key = f"access_paused:{user.id}:{now.isoformat()}"
    queue_email(session, user, "access_paused", key, now=now, details=details)


def restore(session: Session, user: User, now: datetime) -> None:
    """Back to active if they had been accepted; back to the waitlist if not (no email then)."""
    if user.status != "suspended":
        raise AccountError(f'"{user.name}" isn\'t paused (status: {user.status})')
    if user.admitted_at is None:
        user.status = "waitlisted"
        return
    user.status = "active"
    key = f"access_restored:{user.id}:{now.isoformat()}"
    queue_email(session, user, "access_restored", key, now=now)


def set_role(user: User, role: str) -> None:
    if role not in ROLES:
        raise AccountError(f"unknown role {role!r} (roles: {', '.join(ROLES)})")
    user.role = role
