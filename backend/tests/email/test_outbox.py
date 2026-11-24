"""The account email outbox (SPEC_V4 §12.4, §14.3): written with what caused it, sent once,
retried with backoff, never sent when email is off, and no address or body in the logs."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import create_user
from app.config import EmailSettings, Settings
from app.db.models import EmailOutboxRow, User
from app.email.outbox import queue_email, send_pending
from tests.email_fakes import RecordingMail

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
ON = EmailSettings(
    enabled=True, from_address="CoChess <account@mail.example.com>", reply_to="owner@example.com"
)


def _settings(email: EmailSettings = ON) -> Settings:
    return Settings(_env_file=None, public_base_url="https://cochess.example", email=email)


def _player(session: Session, name: str = "Sam", email: str | None = "sam@example.com") -> User:
    user = create_user(session, name)
    user.email = email
    session.commit()
    return user


def _rows(session: Session) -> list[EmailOutboxRow]:
    return list(session.scalars(select(EmailOutboxRow).order_by(EmailOutboxRow.id)))


def test_an_email_is_queued_once_per_dedupe_key(db_session: Session) -> None:
    user = _player(db_session)

    queue_email(db_session, user, "accepted", f"accepted:{user.id}", now=NOW)
    queue_email(db_session, user, "accepted", f"accepted:{user.id}", now=NOW)
    db_session.commit()

    rows = _rows(db_session)
    assert [(r.kind, r.status, r.user_id) for r in rows] == [("accepted", "pending", user.id)]


def test_an_action_that_rolls_back_queues_nothing(db_session: Session) -> None:
    user = _player(db_session)

    queue_email(db_session, user, "accepted", f"accepted:{user.id}", now=NOW)
    db_session.rollback()

    assert _rows(db_session) == []


def test_a_pending_email_is_sent_with_the_name_and_a_link_back(db_session: Session) -> None:
    user = _player(db_session)
    queue_email(db_session, user, "accepted", f"accepted:{user.id}", now=NOW)
    db_session.commit()
    mail = RecordingMail()

    report = send_pending(db_session, _settings(), mail, NOW)

    assert report.sent == 1
    message = mail.to("sam@example.com")[0]
    assert message["From"] == "CoChess <account@mail.example.com>"
    assert message["Reply-To"] == "owner@example.com"
    assert "accepted" in message["Subject"].lower()
    text = message.get_body(("plain",))
    html = message.get_body(("html",))
    assert text is not None and html is not None
    assert "Sam" in text.get_content() and "https://cochess.example" in text.get_content()
    assert "https://cochess.example" in html.get_content()
    row = _rows(db_session)[0]
    assert (row.status, row.sent_at) == ("sent", NOW)


def test_the_name_is_escaped_in_the_html_part(db_session: Session) -> None:
    user = _player(db_session, name="Sam <b>Bold</b>")
    queue_email(db_session, user, "accepted", f"accepted:{user.id}", now=NOW)
    db_session.commit()
    mail = RecordingMail()

    send_pending(db_session, _settings(), mail, NOW)

    html = mail.sent[0].get_body(("html",))
    assert html is not None
    assert "<b>Bold</b>" not in html.get_content()
    assert "&lt;b&gt;Bold&lt;/b&gt;" in html.get_content()


@pytest.mark.parametrize(
    ("email", "address", "reason"),
    [
        (EmailSettings(enabled=False), "sam@example.com", "email is off"),
        (ON, None, "no address on file"),
        (ON.model_copy(update={"allow_list": ["owner@example.com"]}), "sam@example.com", "staging"),
    ],
)
def test_an_email_that_mustnt_go_out_is_skipped(
    db_session: Session, email: EmailSettings, address: str | None, reason: str
) -> None:
    user = _player(db_session, email=address)
    queue_email(db_session, user, "accepted", f"accepted:{user.id}", now=NOW)
    db_session.commit()
    mail = RecordingMail()

    report = send_pending(db_session, _settings(email), mail, NOW)

    assert (report.skipped, mail.attempts) == (1, 0), reason
    assert _rows(db_session)[0].status == "skipped"


def test_a_failed_send_is_retried_later_with_backoff(db_session: Session) -> None:
    user = _player(db_session)
    queue_email(db_session, user, "accepted", f"accepted:{user.id}", now=NOW)
    db_session.commit()
    mail = RecordingMail(fail_times=1)

    first = send_pending(db_session, _settings(), mail, NOW)
    too_soon = send_pending(db_session, _settings(), mail, NOW + timedelta(seconds=30))
    later = send_pending(db_session, _settings(), mail, NOW + timedelta(seconds=61))

    assert (first.retrying, too_soon.sent, later.sent) == (1, 0, 1)
    assert mail.attempts == 2
    assert _rows(db_session)[0].status == "sent"


def test_an_email_that_keeps_failing_is_marked_failed(db_session: Session) -> None:
    user = _player(db_session)
    queue_email(db_session, user, "accepted", f"accepted:{user.id}", now=NOW)
    db_session.commit()
    mail = RecordingMail(fail_times=99)
    settings = _settings(ON.model_copy(update={"max_attempts": 3}))

    when = NOW
    for _ in range(5):
        send_pending(db_session, settings, mail, when)
        when += timedelta(hours=1)

    row = _rows(db_session)[0]
    assert (row.status, row.attempts, mail.attempts) == ("failed", 3, 3)
    assert row.last_error is not None and "sam@example.com" not in row.last_error


def test_logs_name_the_kind_and_user_but_never_the_address_or_body(
    db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    user = _player(db_session)
    queue_email(db_session, user, "accepted", f"accepted:{user.id}", now=NOW)
    db_session.commit()

    with caplog.at_level(logging.INFO, logger="app.email"):
        send_pending(db_session, _settings(), RecordingMail(fail_times=1), NOW)
        send_pending(db_session, _settings(), RecordingMail(), NOW + timedelta(hours=1))

    logged = caplog.text
    assert "accepted" in logged and user.id in logged
    assert "sam@example.com" not in logged and "https://cochess.example" not in logged
