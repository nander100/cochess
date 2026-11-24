"""Sending through SES's SMTP interface, and the background sender (SPEC_V4 §12.4)."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.service import create_user
from app.config import EmailSettings, Settings
from app.db.models import EmailOutboxRow
from app.email import smtp as smtp_module
from app.email.outbox import queue_email
from app.email.smtp import EmailSender, SmtpTransport
from app.main import create_app
from tests.databases import fresh_database_url, is_postgres
from tests.email_fakes import RecordingMail

SES = EmailSettings(
    enabled=True,
    smtp_host="email-smtp.us-east-2.amazonaws.com",
    smtp_port=587,
    smtp_username="ses-user",
    smtp_password="ses-pass",
    from_address="CoChess <account@mail.example.com>",
    poll_seconds=0.05,
)


class FakeSmtp:
    calls: ClassVar[list[tuple[str, Any]]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        FakeSmtp.calls.append(("connect", (host, port, timeout)))

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *_: object) -> None:
        FakeSmtp.calls.append(("quit", None))

    def starttls(self, context: object) -> None:
        FakeSmtp.calls.append(("starttls", context is not None))

    def login(self, user: str, password: str) -> None:
        FakeSmtp.calls.append(("login", (user, password)))

    def send_message(self, message: EmailMessage) -> None:
        FakeSmtp.calls.append(("send", message["To"]))


def test_smtp_sends_encrypted_and_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSmtp.calls = []
    monkeypatch.setattr(smtp_module.smtplib, "SMTP", FakeSmtp)
    message = EmailMessage()
    message["To"] = "sam@example.com"

    SmtpTransport(SES).send(message)

    assert FakeSmtp.calls == [
        ("connect", ("email-smtp.us-east-2.amazonaws.com", 587, SES.timeout_seconds)),
        ("starttls", True),
        ("login", ("ses-user", "ses-pass")),
        ("send", "sam@example.com"),
        ("quit", None),
    ]


def _wait_for(check: Callable[[], bool], seconds: float = 5) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return False


def _threaded_db(tmp_path: Path) -> str:
    """The sender runs on its own thread. In-memory SQLite is one connection shared by every
    thread, so a test's open transaction and the sender's would collide; use a file."""
    return fresh_database_url() if is_postgres() else f"sqlite:///{tmp_path / 'mail.db'}"


def _queue_one(app: Any) -> None:
    with app.state.session_factory() as session:
        user = create_user(session, "Sam")
        user.email = "sam@example.com"
        queue_email(session, user, "accepted", f"accepted:{user.id}", now=datetime.now(UTC))
        session.commit()


def test_the_background_sender_sends_what_is_queued_and_stops_cleanly(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, database_url=_threaded_db(tmp_path), email=SES)
    app = create_app(settings)
    _queue_one(app)
    mail = RecordingMail()

    sender = EmailSender(app.state.session_factory, settings, mail)
    sender.start()
    try:
        assert _wait_for(lambda: len(mail.sent) == 1)
    finally:
        sender.stop()

    assert not sender.running


def test_the_app_runs_the_sender_only_when_email_is_on(tmp_path: Path) -> None:
    off = create_app(Settings(_env_file=None, database_url=fresh_database_url()))
    with TestClient(off):
        assert off.state.email_sender is None

    mail = RecordingMail()
    on = create_app(Settings(_env_file=None, database_url=_threaded_db(tmp_path), email=SES))
    on.state.email_transport = mail
    with TestClient(on):
        assert on.state.email_sender is not None and on.state.email_sender.running
        _queue_one(on)
        assert _wait_for(lambda: len(mail.sent) == 1)

    assert not on.state.email_sender.running
    with on.state.session_factory() as session:
        assert session.scalars(select(EmailOutboxRow.status)).all() == ["sent"]
