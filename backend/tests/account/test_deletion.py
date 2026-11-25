"""Account deletion (SPEC_V4 §11, §14.3): confirmed by typing the name; any live subscription is
cancelled first; one transaction deletes everything that's the player's and keeps money and audit
records without their id; another player's data is untouched; the session ends; one goodbye email
goes to the old address, which is then wiped."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, String, Text, cast, func, select
from sqlalchemy.orm import Session

from app.admin import actions
from app.billing.ledger import grant_trial
from app.config import CreditSettings, EmailSettings, Settings
from app.db.chat import save_turn
from app.db.models import (
    AdminActionRow,
    Base,
    BillingEventRow,
    CreditLedgerRow,
    EmailOutboxRow,
    EmailPreferenceRow,
    LlmUsageRow,
    User,
)
from app.email.outbox import send_pending
from app.legal import accept_terms
from app.main import create_app
from tests import billing_fakes
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import BASE_URL, log_in
from tests.billing_fakes import FakeStripeClient
from tests.coach_fakes import FakeCoachClient
from tests.databases import fresh_database_url
from tests.email_fakes import RecordingMail

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
EMAIL_ON = EmailSettings(enabled=True, from_address="CoChess <account@mail.example.com>")


@pytest.fixture
def app() -> FastAPI:
    settings = Settings(_env_file=None, database_url=fresh_database_url(), email=EMAIL_ON)
    return create_app(settings, FakeCoachClient())


def _user(session: Session, name: str) -> User:
    return session.scalars(select(User).where(User.name == name)).one()


def _full_account(app: FastAPI, name: str, email: str) -> tuple[TestClient, str, str]:
    """A player with a game, a chat, credits, usage, a payment, an owner action, terms and an
    email preference: something in every kind of table."""
    client = log_in(app, name, metered=True)
    client.patch("/api/settings", json={"theme": "dark"})
    game_id = analyzed_game(client, "white")
    with app.state.session_factory() as session:
        user = _user(session, name)
        user.email, user_id = email, user.id
        save_turn(session, game_id, "user", [{"type": "text", "text": "Why?"}], display="Why?")
        grant_trial(session, user, NOW, CreditSettings())
        session.add(
            LlmUsageRow(
                game_id=game_id, user_id=user_id, endpoint="chat", task="chat", model="m",
                input_tokens=1, output_tokens=1, cache_read_tokens=0, cache_write_tokens=0,
                cost_microusd=1234, created_at=NOW,
            )
        )  # fmt: skip
        session.add(
            BillingEventRow(
                provider="stripe", event_id=f"evt_{name}", type="invoice.paid", user_id=user_id,
                amount_cents=1000, currency="usd", outcome="applied", received_at=NOW,
            )
        )  # fmt: skip
        actions.set_metering(session, None, user, unmetered=True, now=NOW)
        accept_terms(session, user, "v1", NOW)
        session.add(EmailPreferenceRow(user_id=user_id, kind="credits_low", enabled=False))
        session.commit()
    return client, user_id, game_id


def _ids_left(session: Session, needle: str) -> list[str]:
    """Every table.column whose text or JSON still contains `needle`."""
    found = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if not isinstance(column.type, (String, Text, JSON)):
                continue
            text = cast(column, String) if isinstance(column.type, JSON) else column
            query = select(func.count()).select_from(table).where(text.contains(needle))
            if session.scalar(query):
                found.append(f"{table.name}.{column.name}")
    return found


def _delete(client: TestClient, name: str) -> Any:
    return client.request("DELETE", "/api/me", json={"confirm_name": name})


def _set(app: FastAPI, user_id: str, **values: Any) -> None:
    with app.state.session_factory() as session:
        user = session.get(User, user_id)
        assert user is not None
        for key, value in values.items():
            setattr(user, key, value)
        session.commit()


def test_deleting_leaves_no_trace_but_anonymous_money_and_audit_rows(app: FastAPI) -> None:
    keep_client, keep_id, keep_game = _full_account(app, "Keep", "keep@example.com")
    client, user_id, game_id = _full_account(app, "Gone", "gone@example.com")

    response = _delete(client, "gone")  # any case

    assert response.status_code == 204
    assert client.get("/api/me").status_code == 401  # signed out everywhere
    with app.state.session_factory() as session:
        assert _ids_left(session, user_id) == []
        assert _ids_left(session, game_id) == []
        assert session.get(User, user_id) is None
        kept = session.scalars(select(LlmUsageRow).where(LlmUsageRow.cost_microusd == 1234))
        assert sorted(((r.user_id or ""), (r.game_id or "")) for r in kept) == sorted(
            [("", ""), (keep_id, keep_game)]
        )
        anonymous_payments = select(func.count()).select_from(BillingEventRow)
        assert session.scalar(anonymous_payments.where(BillingEventRow.user_id.is_(None))) == 1
        trials = session.scalars(select(CreditLedgerRow).where(CreditLedgerRow.kind == "trial"))
        assert sorted(r.user_id is None for r in trials) == [False, True]
        audits = session.scalars(select(AdminActionRow))
        assert sorted(a.target_user_id is None for a in audits) == [False, True]
    assert keep_client.get("/api/me").status_code == 200
    assert keep_client.get(f"/api/games/{keep_game}").status_code == 200


def test_one_goodbye_email_goes_to_the_old_address_then_the_address_is_wiped(
    app: FastAPI,
) -> None:
    client, _, _ = _full_account(app, "Gone", "gone@example.com")
    assert _delete(client, "Gone").status_code == 204

    with app.state.session_factory() as session:
        [row] = session.scalars(select(EmailOutboxRow)).all()  # the player's other emails went
        assert (row.kind, row.user_id, row.to_address) == (
            "account_deleted", None, "gone@example.com",
        )  # fmt: skip
        mail = RecordingMail()
        send_pending(session, app.state.settings, mail, datetime.now(UTC))
        session.refresh(row)
        assert (row.status, row.to_address, row.details) == ("sent", None, {})
    [message] = mail.to("gone@example.com")
    body = message.get_body(("plain",))
    assert body is not None and "Gone" in body.get_content()


def test_a_wrong_name_deletes_nothing(app: FastAPI) -> None:
    client, user_id, _ = _full_account(app, "Careful", "careful@example.com")

    response = _delete(client, "Someone else")

    assert response.status_code == 422
    assert "type your name" in response.json()["detail"]
    with app.state.session_factory() as session:
        assert session.get(User, user_id) is not None


def test_a_live_subscription_is_cancelled_first(app: FastAPI) -> None:
    fake = billing_fakes.install(app, FakeStripeClient())
    fake.subscriptions.listed = [SimpleNamespace(id="sub_9", status="active")]
    client, user_id, _ = _full_account(app, "Payer", "payer@example.com")
    _set(app, user_id, billing_customer_id="cus_9", subscription_status="active")

    assert _delete(client, "Payer").status_code == 204

    assert fake.params("subscriptions.cancel") == ["sub_9"]


def test_when_stripe_wont_cancel_nothing_is_deleted(app: FastAPI) -> None:
    fake = billing_fakes.install(app, FakeStripeClient())

    def refuse(params: object) -> object:
        raise RuntimeError("stripe is down")

    fake.subscriptions.list = refuse  # type: ignore[method-assign]
    client, user_id, _ = _full_account(app, "Payer", "payer@example.com")
    _set(app, user_id, billing_customer_id="cus_9", subscription_status="active")

    assert _delete(client, "Payer").status_code == 502

    with app.state.session_factory() as session:
        assert session.get(User, user_id) is not None
    assert client.get("/api/me").status_code == 200


def test_an_owner_cant_delete_their_own_account(app: FastAPI) -> None:
    client, user_id, _ = _full_account(app, "Boss", "boss@example.com")
    _set(app, user_id, role="owner")

    assert _delete(client, "Boss").status_code == 409


def test_a_waitlisted_account_can_delete_itself(app: FastAPI) -> None:
    client = log_in(app, "Waiting")
    with app.state.session_factory() as session:
        _user(session, "Waiting").status = "waitlisted"
        session.commit()

    assert _delete(client, "Waiting").status_code == 204


def test_deleting_needs_a_login(app: FastAPI) -> None:
    anonymous = TestClient(app, base_url=BASE_URL)
    assert anonymous.request("DELETE", "/api/me", json={"confirm_name": "x"}).status_code == 401
