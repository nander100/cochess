"""The account email outbox (SPEC_V4 §12.4).

`queue_email` adds a row in the caller's transaction, so an email exists exactly when what caused
it was committed; a dedupe key makes each one go out once. `send_pending` sends what's due:
skipped when email is off, there's no address, or (staging) the address isn't allowed; retried
with doubling waits when sending fails, and marked failed after the last attempt. Logs name the
kind, the user and the status, never the address or the body.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from string import Template
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import EmailOutboxRow, User
from app.email.templates import TEXTS, escape, to_html

log = logging.getLogger("app.email")


@dataclass(frozen=True)
class EmailKind:
    subject: str
    can_turn_off: bool = False  # SPEC_V4 §12.4: only the credit emails can be turned off (M7)


EMAILS: dict[str, EmailKind] = {
    "waitlist_joined": EmailKind("You're on the CoChess waitlist"),
    "accepted": EmailKind("You've been accepted to CoChess"),
    "access_paused": EmailKind("Your CoChess access is paused"),
    "access_restored": EmailKind("Your CoChess access is back"),
    "terms_updated": EmailKind("We've updated the CoChess terms"),
}


class MailTransport(Protocol):
    def send(self, message: EmailMessage) -> None: ...


@dataclass(frozen=True)
class SendReport:
    sent: int = 0
    skipped: int = 0
    retrying: int = 0
    failed: int = 0


def queue_email(
    session: Session,
    user: User,
    kind: str,
    dedupe_key: str,
    *,
    now: datetime,
    details: dict[str, str] | None = None,
) -> None:
    """Add the email to the caller's transaction (not committed here). A repeat key is a no-op."""
    if kind not in EMAILS:
        raise ValueError(f"unknown email kind {kind!r}")
    pending = any(
        isinstance(obj, EmailOutboxRow) and obj.dedupe_key == dedupe_key for obj in session.new
    )
    queued = session.scalar(
        select(EmailOutboxRow.id).where(EmailOutboxRow.dedupe_key == dedupe_key)
    )
    if pending or queued is not None:
        return
    session.add(
        EmailOutboxRow(
            user_id=user.id,
            kind=kind,
            dedupe_key=dedupe_key,
            details=details or {},
            next_attempt_at=now,
            created_at=now,
        )
    )


def send_pending(
    session: Session, settings: Settings, transport: MailTransport, now: datetime
) -> SendReport:
    """Send the emails that are due, oldest first, and commit each row's outcome."""
    rows = session.scalars(
        select(EmailOutboxRow)
        .where(EmailOutboxRow.status == "pending", EmailOutboxRow.next_attempt_at <= now)
        .order_by(EmailOutboxRow.id)
        .limit(settings.email.batch_size)
    ).all()
    counts = {"sent": 0, "skipped": 0, "retrying": 0, "failed": 0}
    for row in rows:
        outcome = _send_one(session, settings, transport, row, now)
        counts[outcome] += 1
        session.commit()
        log.info("email %s (row %s) for user %s: %s", row.kind, row.id, row.user_id, outcome)
    return SendReport(**counts)


def _send_one(
    session: Session,
    settings: Settings,
    transport: MailTransport,
    row: EmailOutboxRow,
    now: datetime,
) -> str:
    user = session.get(User, row.user_id) if row.user_id else None
    address = user.email if user is not None else None
    allowed = {entry.casefold() for entry in settings.email.allow_list}
    if (
        not settings.email.enabled
        or user is None
        or not address
        or (allowed and address.casefold() not in allowed)
    ):
        row.status = "skipped"
        return "skipped"
    try:
        transport.send(compose(row, user, address, settings))
    except Exception as error:  # any transport failure: retry later, never lose the row
        row.attempts += 1
        row.last_error = type(error).__name__[:200]  # the message may hold the address
        if row.attempts >= settings.email.max_attempts:
            row.status = "failed"
            return "failed"
        wait = settings.email.retry_seconds * 2 ** (row.attempts - 1)
        row.next_attempt_at = now + timedelta(seconds=wait)
        return "retrying"
    row.attempts += 1
    row.status, row.sent_at = "sent", now
    return "sent"


def compose(row: EmailOutboxRow, user: User, address: str, settings: Settings) -> EmailMessage:
    kind = EMAILS[row.kind]
    values = {
        "name": user.name,
        "app_url": settings.public_base_url.rstrip("/"),
        "note": row.details.get("note", ""),
    }
    message = EmailMessage()
    message["From"] = settings.email.from_address
    message["To"] = address
    if settings.email.reply_to:
        message["Reply-To"] = settings.email.reply_to
    message["Subject"] = kind.subject
    template = Template(TEXTS[row.kind])
    message.set_content(template.safe_substitute(values))
    escaped = {key: escape(value) for key, value in values.items()}
    message.add_alternative(
        to_html(template.safe_substitute(escaped), escaped["app_url"]), subtype="html"
    )
    return message
