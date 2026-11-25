"""The credit emails and the ones a player can turn off (SPEC_V4 §12.4): credits_low and
credits_out at most once per grant (trial, allowance or top-up), never for an unmetered player;
credits_added when the owner adds credits, with the note only if ticked; preferences and the
signed one-click unsubscribe link."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import actions
from app.auth.service import create_user
from app.billing.ledger import charge_usage, grant_trial
from app.billing.notices import notify_balance
from app.config import CreditSettings, EmailSettings, Settings
from app.db.models import EmailOutboxRow, EmailPreferenceRow, User
from app.email.outbox import send_pending
from app.email.preferences import unsubscribe_token
from app.main import create_app
from tests.auth_helpers import BASE_URL, log_in
from tests.coach_fakes import FakeCoachClient
from tests.databases import fresh_database_url
from tests.email_fakes import RecordingMail

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
CREDIT = 10_000
EMAIL_ON = EmailSettings(
    enabled=True, from_address="CoChess <account@mail.example.com>", link_secret="test-secret"
)


@pytest.fixture
def app() -> FastAPI:
    settings = Settings(
        _env_file=None,
        database_url=fresh_database_url(),
        public_base_url="https://cochess.example",
        email=EMAIL_ON,
    )
    return create_app(settings, FakeCoachClient())


def _player(session: Session, name: str = "Sam") -> User:
    user = create_user(session, name)
    user.email = f"{name.lower()}@example.com"
    grant_trial(session, user, NOW, CreditSettings())  # 50 credits
    session.commit()
    return user


def _kinds(session: Session) -> list[str]:
    return [r.kind for r in session.scalars(select(EmailOutboxRow).order_by(EmailOutboxRow.id))]


def _spend(session: Session, app: FastAPI, user: User, credits: float, n: int) -> None:
    charge_usage(session, user.id, n, round(credits * CREDIT), NOW)
    notify_balance(session, user, app.state.settings, NOW)
    session.commit()


def _plain(message: object) -> str:
    body = message.get_body(("plain",))  # type: ignore[attr-defined]
    assert body is not None
    return str(body.get_content())


def test_low_then_out_each_once_per_grant(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        user = _player(session)
        _spend(session, app, user, 20, 1)  # 30 left: fine
        assert _kinds(session) == []
        _spend(session, app, user, 22, 2)  # 8 left: under 20% of the 50-credit trial
        _spend(session, app, user, 1, 3)  # still low: not again
        assert _kinds(session) == ["credits_low"]
        _spend(session, app, user, 8, 4)  # out
        _spend(session, app, user, 1, 5)
        assert _kinds(session) == ["credits_low", "credits_out"]
        # An owner grant isn't a new period: running low on it again sends nothing more.
        credits = CreditSettings()
        actions.change_credits(session, None, user, 50, note="refill", now=NOW, settings=credits)
        _spend(session, app, user, 45, 6)
        assert _kinds(session).count("credits_low") == 1


def test_an_unmetered_player_gets_no_credit_warnings(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        user = _player(session)
        user.unmetered = True
        _spend(session, app, user, 60, 1)
        assert _kinds(session) == []


def test_credits_added_carries_the_note_only_when_ticked(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        user = _player(session)
        credits = CreditSettings()
        actions.change_credits(session, None, user, 25, note="private", now=NOW, settings=credits)
        actions.change_credits(
            session, None, user, 10, note="Thanks for testing!", now=NOW, settings=credits,
            email_note=True,
        )  # fmt: skip
        actions.change_credits(session, None, user, -5, note="oops", now=NOW, settings=credits)
        session.commit()
        mail = RecordingMail()
        send_pending(session, app.state.settings, mail, NOW)

    bodies = [_plain(m) for m in mail.sent]
    assert len(bodies) == 2  # a removal sends nothing
    assert "25 coaching credits" in bodies[0] and "private" not in bodies[0]
    assert "10 coaching credits" in bodies[1] and "Thanks for testing!" in bodies[1]


def test_a_turned_off_email_is_skipped_when_it_would_be_sent(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        user = _player(session)
        _spend(session, app, user, 45, 1)  # credits_low queued
        session.add(EmailPreferenceRow(user_id=user.id, kind="credits_low", enabled=False))
        session.commit()
        mail = RecordingMail()
        send_pending(session, app.state.settings, mail, NOW)
        [row] = session.scalars(select(EmailOutboxRow)).all()
        assert row.status == "skipped" and mail.sent == []


def test_each_optional_email_has_a_one_click_unsubscribe_link(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        user = _player(session)
        _spend(session, app, user, 45, 1)
        mail = RecordingMail()
        send_pending(session, app.state.settings, mail, NOW)
        token = unsubscribe_token(app.state.settings.email, user.id, "credits_balance")
    [message] = mail.sent
    assert f"https://cochess.example/unsubscribe?token={token}" in _plain(message)
    assert message["List-Unsubscribe"] == (
        f"<https://cochess.example/api/email/unsubscribe?token={token}>"
    )
    assert message["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_unsubscribing_turns_off_that_group_only(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        user_id = _player(session).id
    token = unsubscribe_token(app.state.settings.email, user_id, "credits_balance")
    anonymous = TestClient(app, base_url=BASE_URL)

    response = anonymous.post(f"/api/email/unsubscribe?token={token}")

    assert response.status_code == 200
    assert response.json() == {"group": "credits_balance"}
    with app.state.session_factory() as session:
        rows = session.scalars(
            select(EmailPreferenceRow).where(EmailPreferenceRow.user_id == user_id)
        )
        prefs = {p.kind: p.enabled for p in rows}
    assert prefs == {"credits_low": False, "credits_out": False}


@pytest.mark.parametrize("token", ["", "garbage", "dXNlcjpjcmVkaXRzX2JhbGFuY2U.forged"])
def test_a_bad_unsubscribe_token_changes_nothing(app: FastAPI, token: str) -> None:
    response = TestClient(app, base_url=BASE_URL).post(f"/api/email/unsubscribe?token={token}")

    assert response.status_code == 400
    with app.state.session_factory() as session:
        assert session.scalars(select(EmailPreferenceRow)).all() == []


def test_a_player_reads_and_changes_their_email_preferences(app: FastAPI) -> None:
    client = log_in(app, "Prefs")

    assert client.get("/api/me/email").json() == {
        "preferences": {"credits_balance": True, "credits_added": True}
    }
    changed = client.patch("/api/me/email", json={"credits_added": False})

    assert changed.json()["preferences"] == {"credits_balance": True, "credits_added": False}
    assert client.get("/api/me/email").json()["preferences"]["credits_added"] is False
    assert client.patch("/api/me/email", json={"accepted": False}).status_code == 422
