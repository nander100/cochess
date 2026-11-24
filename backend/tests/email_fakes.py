"""Mail transports for tests (SPEC_V4 §14.3): never send real mail."""

from dataclasses import dataclass, field
from email.message import EmailMessage


@dataclass
class RecordingMail:
    """Keeps every message it's asked to send. `fail_times` makes the first sends fail."""

    sent: list[EmailMessage] = field(default_factory=list)
    fail_times: int = 0
    attempts: int = 0

    def send(self, message: EmailMessage) -> None:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise ConnectionError(f"SMTP refused {message['To']}")  # an address in the error
        self.sent.append(message)

    def to(self, address: str) -> list[EmailMessage]:
        return [message for message in self.sent if message["To"] == address]
