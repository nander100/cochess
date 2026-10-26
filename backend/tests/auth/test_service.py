from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import (
    InvalidInviteError,
    UserExistsError,
    create_invite,
    create_user,
    end_session,
    find_user,
    hash_token,
    redeem_invite,
    session_user,
)
from app.config import AuthSettings
from app.db.models import AuthSession, Invite

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
SETTINGS = AuthSettings()


def test_create_user_strips_the_name_and_finds_it_ignoring_case(db_session: Session) -> None:
    user = create_user(db_session, "  Alex ")

    assert user.name == "Alex"
    assert find_user(db_session, "alex") == user
    assert find_user(db_session, "Sam") is None


def test_create_user_rejects_duplicate_names_ignoring_case(db_session: Session) -> None:
    create_user(db_session, "Alex")

    with pytest.raises(UserExistsError):
        create_user(db_session, "ALEX")


@pytest.mark.parametrize("name", ["", "   ", "x" * 61])
def test_create_user_rejects_empty_or_long_names(db_session: Session, name: str) -> None:
    with pytest.raises(ValueError, match="1 to 60"):
        create_user(db_session, name)


def test_invite_stores_only_a_hash_of_a_long_random_token(db_session: Session) -> None:
    user = create_user(db_session, "Alex")

    token = create_invite(db_session, user, NOW, SETTINGS)

    assert len(token) >= 43  # 32 bytes, URL-safe base64
    invite = db_session.scalars(select(Invite)).one()
    assert invite.token_hash == hash_token(token)
    assert token not in invite.token_hash
    assert invite.expires_at == NOW + timedelta(days=7)


def test_redeem_starts_a_30_day_session_for_the_invited_user(db_session: Session) -> None:
    user = create_user(db_session, "Alex")
    invite = create_invite(db_session, user, NOW, SETTINGS)

    token = redeem_invite(db_session, invite, NOW, SETTINGS)

    assert session_user(db_session, token, NOW) == user
    row = db_session.scalars(select(AuthSession)).one()
    assert row.token_hash == hash_token(token)
    assert row.expires_at == NOW + timedelta(days=30)


def test_an_invite_works_only_once(db_session: Session) -> None:
    user = create_user(db_session, "Alex")
    invite = create_invite(db_session, user, NOW, SETTINGS)
    redeem_invite(db_session, invite, NOW, SETTINGS)

    with pytest.raises(InvalidInviteError):
        redeem_invite(db_session, invite, NOW, SETTINGS)


def test_an_invite_expires_after_7_days(db_session: Session) -> None:
    user = create_user(db_session, "Alex")
    invite = create_invite(db_session, user, NOW, SETTINGS)

    with pytest.raises(InvalidInviteError):
        redeem_invite(db_session, invite, NOW + timedelta(days=7), SETTINGS)


def test_an_unknown_invite_is_rejected(db_session: Session) -> None:
    with pytest.raises(InvalidInviteError):
        redeem_invite(db_session, "not-a-token", NOW, SETTINGS)


def test_a_session_expires_after_30_days(db_session: Session) -> None:
    user = create_user(db_session, "Alex")
    token = redeem_invite(db_session, create_invite(db_session, user, NOW, SETTINGS), NOW, SETTINGS)

    assert session_user(db_session, token, NOW + timedelta(days=29)) == user
    assert session_user(db_session, token, NOW + timedelta(days=30)) is None


def test_ending_a_session_logs_out_only_that_browser(db_session: Session) -> None:
    user = create_user(db_session, "Alex")
    first = redeem_invite(db_session, create_invite(db_session, user, NOW, SETTINGS), NOW, SETTINGS)
    second = redeem_invite(
        db_session, create_invite(db_session, user, NOW, SETTINGS), NOW, SETTINGS
    )

    end_session(db_session, first)

    assert session_user(db_session, first, NOW) is None
    assert session_user(db_session, second, NOW) == user


def test_an_unknown_session_token_has_no_user(db_session: Session) -> None:
    assert session_user(db_session, "nope", NOW) is None
