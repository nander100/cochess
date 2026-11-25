"""The emails a player can turn off (SPEC_V4 §12.4), in two groups: the low and out of credits
warnings, and the credits-added notice. Each optional email carries a signed one-click link
(no login): the token names the player and the group, signed with EMAIL__LINK_SECRET."""

import base64
import hashlib
import hmac
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import EmailSettings
from app.db.models import EmailPreferenceRow

GROUPS: dict[str, tuple[str, ...]] = {
    "credits_balance": ("credits_low", "credits_out"),
    "credits_added": ("credits_added",),
}
GROUP_OF = {kind: group for group, kinds in GROUPS.items() for kind in kinds}
_SIGNATURE = 32  # hex characters of the HMAC kept in the link


def unsubscribe_token(settings: EmailSettings, user_id: str, group: str) -> str:
    payload = base64.urlsafe_b64encode(f"{user_id}:{group}".encode()).decode().rstrip("=")
    return f"{payload}.{_sign(settings, payload)}"


def read_token(settings: EmailSettings, token: str) -> tuple[str, str] | None:
    """(user id, group) from a genuine token; None for anything else."""
    payload, _, signature = token.partition(".")
    if not payload or not hmac.compare_digest(signature, _sign(settings, payload)):
        return None
    try:
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()
    except ValueError:
        return None
    user_id, _, group = decoded.partition(":")
    return (user_id, group) if user_id and group in GROUPS else None


def is_enabled(session: Session, user_id: str, kind: str) -> bool:
    row = session.get(EmailPreferenceRow, (user_id, kind))
    return row is None or row.enabled


def preferences(session: Session, user_id: str) -> dict[str, bool]:
    rows = session.scalars(select(EmailPreferenceRow).where(EmailPreferenceRow.user_id == user_id))
    off = {row.kind for row in rows if not row.enabled}
    return {group: not off.intersection(kinds) for group, kinds in GROUPS.items()}


def set_group(session: Session, user_id: str, group: str, enabled: bool, now: datetime) -> None:
    """Turn a group's emails on or off (in the caller's transaction)."""
    for kind in GROUPS[group]:
        row = session.get(EmailPreferenceRow, (user_id, kind))
        if row is None:
            session.add(
                EmailPreferenceRow(user_id=user_id, kind=kind, enabled=enabled, updated_at=now)
            )
        else:
            row.enabled, row.updated_at = enabled, now


def _sign(settings: EmailSettings, payload: str) -> str:
    digest = hmac.new(settings.link_secret.encode(), payload.encode(), hashlib.sha256)
    return digest.hexdigest()[:_SIGNATURE]
