"""The account email outbox (SPEC_V4 §12.4).

`queue_email` adds a row in the caller's transaction, so an email exists exactly when what caused
it was committed; a dedupe key makes each one go out once. `send_pending` sends what's due:
skipped when email is off, there's no address, or (staging) the address isn't allowed; retried
with doubling waits when sending fails, and marked failed after the last attempt. Logs name the
kind, the user and the status, never the address or the body.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from string import Template
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import EmailOutboxRow, User
from app.email.preferences import GROUP_OF, is_enabled, unsubscribe_token
from app.email.templates import TEXTS, escape, to_html

log = logging.getLogger("app.email")


@dataclass(frozen=True)
class EmailKind:
    subject: str
    can_turn_off: bool = False  # SPEC_V4 §12.4: only the credit emails can be turned off


EMAILS: dict[str, EmailKind] = {
    "waitlist_joined": EmailKind("You're on the CoChess waitlist"),
    "accepted": EmailKind("You've been accepted to CoChess"),
    "access_paused": EmailKind("Your CoChess access is paused"),
    "access_restored": EmailKind("Your CoChess access is back"),
    "terms_updated": EmailKind("We've updated the CoChess terms"),
    "account_deleted": EmailKind("Your CoChess account has been deleted"),
    "credits_low": EmailKind("You're running low on CoChess credits", can_turn_off=True),
    "credits_out": EmailKind("You're out of CoChess credits", can_turn_off=True),
    "credits_added": EmailKind("Coaching credits were added to your account", can_turn_off=True),
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


def queue_farewell(session: Session, address: str, name: str, now: datetime) -> None:
    """The account_deleted email (SPEC_V4 §11), for an account that's about to be gone: it carries
    its own address and name, both wiped once the row is finished (`_finish`)."""
    session.add(
        EmailOutboxRow(
            user_id=None,
            kind="account_deleted",
            dedupe_key=f"account_deleted:{uuid.uuid4()}",
            details={"name": name},
            to_address=address,
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
        if outcome != "retrying" and row.to_address is not None:
            row.to_address, row.details = None, {}  # a deleted account's address and name go
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
    address = user.email if user is not None else row.to_address
    name = user.name if user is not None else row.details.get("name", "")
    allowed = {entry.casefold() for entry in settings.email.allow_list}
    if (
        not settings.email.enabled
        or not address
        or (user is None and row.to_address is None)
        or (allowed and address.casefold() not in allowed)
        or (user is not None and EMAILS[row.kind].can_turn_off
            and not is_enabled(session, user.id, row.kind))
    ):  # fmt: skip
        row.status = "skipped"
        return "skipped"
    try:
        transport.send(compose(row, name, address, settings))
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


def compose(row: EmailOutboxRow, name: str, address: str, settings: Settings) -> EmailMessage:
    kind = EMAILS[row.kind]
    app_url = settings.public_base_url.rstrip("/")
    values = {
        "name": name,
        "app_url": app_url,
        "note": row.details.get("note", ""),
        "credits": row.details.get("credits", ""),
    }
    message = EmailMessage()
    message["From"] = settings.email.from_address
    message["To"] = address
    if settings.email.reply_to:
        message["Reply-To"] = settings.email.reply_to
    message["Subject"] = kind.subject
    text = TEXTS[row.kind]
    if kind.can_turn_off and row.user_id:
        # One-click unsubscribe (SPEC_V4 §12.4): a link in the text, and RFC 8058 headers so
        # mail apps can offer their own button.
        token = unsubscribe_token(settings.email, row.user_id, GROUP_OF[row.kind])
        text += f"\nDon't want these emails? Turn them off: {app_url}/unsubscribe?token={token}\n"
        message["List-Unsubscribe"] = f"<{app_url}/api/email/unsubscribe?token={token}>"
        message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    template = Template(text)
    message.set_content(template.safe_substitute(values))
    escaped = {key: escape(value) for key, value in values.items()}
    message.add_alternative(
        to_html(template.safe_substitute(escaped), escaped["app_url"]), subtype="html"
    )
    return message
