"""Users, one-time invite links, and login sessions. Only hashes of tokens are stored."""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import AuthSettings
from app.db.models import AuthSession, Invite, User

TOKEN_BYTES = 32  # SPEC_V2 §4.1: at least 32 random bytes, URL-safe
MAX_NAME_CHARS = 60


class UserExistsError(Exception):
    pass


class InvalidInviteError(Exception):
    """The invite token is unknown, already used, or expired."""


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def name_key(name: str) -> str:
    return name.strip().casefold()


def create_user(session: Session, name: str) -> User:
    clean = name.strip()
    if not clean or len(clean) > MAX_NAME_CHARS:
        raise ValueError(f"A name must be 1 to {MAX_NAME_CHARS} characters long.")
    if find_user(session, clean) is not None:
        raise UserExistsError(clean)
    user = User(name=clean, name_key=name_key(clean))
    session.add(user)
    session.commit()
    return user


def find_user(session: Session, name: str) -> User | None:
    return session.scalars(select(User).where(User.name_key == name_key(name))).first()


def create_invite(session: Session, user: User, now: datetime, settings: AuthSettings) -> str:
    """A new one-time login token for `user`. Returns the raw token (shown once, never stored)."""
    token = new_token()
    session.add(
        Invite(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(days=settings.invite_ttl_days),
            created_at=now,
        )
    )
    session.commit()
    return token


def redeem_invite(session: Session, token: str, now: datetime, settings: AuthSettings) -> str:
    """Use up an invite and start a session. Returns the raw session token for the cookie."""
    invite = session.scalars(select(Invite).where(Invite.token_hash == hash_token(token))).first()
    if invite is None or invite.used_at is not None or invite.expires_at <= now:
        raise InvalidInviteError
    # Conditional update, so two simultaneous redeems can't both succeed.
    claimed = session.execute(
        update(Invite).where(Invite.id == invite.id, Invite.used_at.is_(None)).values(used_at=now)
    )
    if claimed.rowcount != 1:  # type: ignore[attr-defined]
        session.rollback()
        raise InvalidInviteError
    raw = new_token()
    session.add(
        AuthSession(
            user_id=invite.user_id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(days=settings.session_ttl_days),
            created_at=now,
        )
    )
    session.commit()
    return raw


def session_user(session: Session, token: str, now: datetime) -> User | None:
    """The user a session token belongs to, if the session exists and hasn't expired."""
    row = session.scalars(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    ).first()
    if row is None or row.expires_at <= now:
        return None
    return session.get(User, row.user_id)


def end_session(session: Session, token: str) -> None:
    row = session.scalars(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()
