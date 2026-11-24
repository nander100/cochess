"""Sending account email (SPEC_V4 §12.4): Amazon SES's SMTP interface with the standard library,
and a background thread that sends what's due every few seconds. Neither logs the SMTP password,
addresses or bodies."""

import logging
import smtplib
import ssl
import threading
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy.orm import Session, sessionmaker

from app.config import EmailSettings, Settings
from app.email.outbox import MailTransport, send_pending

log = logging.getLogger("app.email")


class SmtpTransport:
    """One connection per message: account email is rare, and SES closes idle connections."""

    def __init__(self, settings: EmailSettings) -> None:
        self._settings = settings

    def send(self, message: EmailMessage) -> None:
        settings = self._settings
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=settings.timeout_seconds
        ) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)


class EmailSender:
    """Runs `send_pending` every `poll_seconds` on its own thread until `stop()`."""

    def __init__(
        self, session_factory: sessionmaker[Session], settings: Settings, transport: MailTransport
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._transport = transport
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="email-sender", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._settings.email.timeout_seconds + 5)

    def _run(self) -> None:
        while True:
            try:
                with self._session_factory() as session:
                    send_pending(session, self._settings, self._transport, datetime.now(UTC))
            except Exception:  # keep the loop alive; the row stays pending for the next pass
                log.exception("email sender pass failed")
            if self._stop.wait(self._settings.email.poll_seconds):
                return
