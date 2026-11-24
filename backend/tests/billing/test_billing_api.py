"""Paying through the API (SPEC_V4 §6.2, §14.3): checkout and the portal, and the webhook as the
only place money becomes credits: signature checked, each event applied once, out-of-order and
refunded events handled, the browser never trusted."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing.ledger import balance, charge_usage, grant_allowance
from app.db.models import BillingEventRow, User
from tests.auth_helpers import log_in
from tests.billing_fakes import (
    charge_refunded,
    install,
    invoice_paid,
    sign,
    subscription,
    top_up_completed,
)

CREDIT = 10_000
CUSTOMER = "cus_test_1"
SOON = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
LATER = SOON + 30 * 86_400


def _user(session: Session, name: str) -> User:
    return session.scalars(select(User).where(User.name == name)).one()


def _player(app: FastAPI, name: str = "Sam", customer: str | None = CUSTOMER) -> TestClient:
    client = log_in(app, name, metered=True)
    with app.state.session_factory() as session:
        _user(session, name).billing_customer_id = customer
        session.commit()
    return client


def _user_id(app: FastAPI, name: str = "Sam") -> str:
    with app.state.session_factory() as session:
        return _user(session, name).id


def _credits(app: FastAPI, name: str = "Sam") -> float:
    with app.state.session_factory() as session:
        return balance(session, _user(session, name).id).total / CREDIT


def _post(anon: TestClient, payload: bytes, signature: str | None = None) -> int:
    header = sign(payload) if signature is None else signature
    response = anon.post(
        "/api/billing/webhook",
        content=payload,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )
    return response.status_code


@pytest.fixture
def paying(app: FastAPI) -> FastAPI:
    install(app)
    return app


# Checkout and portal


def test_checkout_answers_503_while_payments_are_off(app: FastAPI) -> None:
    client = _player(app)

    response = client.post("/api/billing/checkout", json={"product": "top_up"})

    assert response.status_code == 503


def test_checkout_returns_the_payment_page_and_remembers_the_customer(app: FastAPI) -> None:
    fake = install(app)
    client = _player(app, customer=None)

    response = client.post("/api/billing/checkout", json={"product": "monthly"})

    assert response.status_code == 200
    assert response.json()["url"].startswith("https://stripe.test/checkout/")
    [params] = fake.params("checkout.create")
    assert params["success_url"].endswith("/billing/return?product=monthly")
    with app.state.session_factory() as session:
        user = _user(session, "Sam")
        assert (user.billing_customer_id, user.billing_provider) == ("cus_test_1", "stripe")


def test_checkout_takes_only_known_products(paying: FastAPI) -> None:
    client = _player(paying)

    response = client.post("/api/billing/checkout", json={"product": "free_stuff"})

    assert response.status_code == 422


def test_a_second_subscription_is_refused(paying: FastAPI) -> None:
    client = _player(paying)
    with paying.state.session_factory() as session:
        _user(session, "Sam").subscription_status = "active"
        session.commit()

    assert client.post("/api/billing/checkout", json={"product": "monthly"}).status_code == 409
    assert client.post("/api/billing/checkout", json={"product": "top_up"}).status_code == 200


def test_the_portal_needs_a_customer(paying: FastAPI) -> None:
    newcomer = _player(paying, "New", customer=None)
    payer = _player(paying, "Payer", customer="cus_payer")

    assert newcomer.post("/api/billing/portal").status_code == 409
    response = payer.post("/api/billing/portal")
    assert response.status_code == 200
    assert response.json()["url"].startswith("https://stripe.test/portal/")


def test_checkout_needs_a_login(paying: FastAPI, anon_client: TestClient) -> None:
    response = anon_client.post("/api/billing/checkout", json={"product": "top_up"})

    assert response.status_code == 401


def test_billing_shows_products_subscription_and_the_guardian_note(paying: FastAPI) -> None:
    client = _player(paying)
    with paying.state.session_factory() as session:
        user = _user(session, "Sam")
        user.age_band = "13_17"
        user.subscription_status = "active"
        session.commit()

    body = client.get("/api/billing").json()

    assert body["payments_enabled"] is True
    assert body["has_billing_account"] is True
    assert body["subscription"]["status"] == "active"
    assert body["needs_guardian"] is True
    assert [(p["key"], p["credits"], p["price_cents"]) for p in body["products"]] == [
        ("monthly", 300, 1000),
        ("top_up", 150, 500),
    ]


# Webhooks


def test_a_paid_top_up_adds_150_lasting_credits_once(
    paying: FastAPI, anon_client: TestClient
) -> None:
    _player(paying)
    payload = top_up_completed("evt_1", _user_id(paying), CUSTOMER)

    assert _post(anon_client, payload) == 200
    assert _post(anon_client, payload) == 200  # Stripe resends: acknowledged, ignored

    assert _credits(paying) == 150
    with paying.state.session_factory() as session:
        row = session.scalars(select(BillingEventRow)).one()
    assert (row.outcome, row.amount_cents, row.currency) == ("applied", 500, "usd")


def test_a_badly_signed_webhook_is_refused_and_changes_nothing(
    paying: FastAPI, anon_client: TestClient
) -> None:
    _player(paying)
    payload = top_up_completed("evt_1", _user_id(paying), CUSTOMER)

    assert _post(anon_client, payload, signature="t=1,v1=forged") == 400

    assert _credits(paying) == 0
    with paying.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(BillingEventRow)) == 0


def test_the_webhook_answers_503_while_payments_are_off(
    app: FastAPI, anon_client: TestClient
) -> None:
    assert _post(anon_client, top_up_completed("evt_1", "x", CUSTOMER)) == 503


def test_each_paid_period_replaces_the_last_allowance(
    paying: FastAPI, anon_client: TestClient
) -> None:
    client = _player(paying)
    _post(anon_client, subscription("evt_s", "created", CUSTOMER, "active", SOON))
    _post(anon_client, invoice_paid("evt_1", CUSTOMER, "in_1", SOON))
    assert _credits(paying) == 300

    _post(anon_client, invoice_paid("evt_2", CUSTOMER, "in_2", LATER))
    _post(anon_client, invoice_paid("evt_2b", CUSTOMER, "in_2", LATER))  # same invoice again

    assert _credits(paying) == 300  # the unused 300 went; the new 300 came, once
    body = client.get("/api/billing").json()
    assert body["allowance_credits"] == 300
    assert body["subscription"]["status"] == "active"


def test_an_invoice_before_its_subscription_event_still_counts(
    paying: FastAPI, anon_client: TestClient
) -> None:
    _player(paying)

    _post(anon_client, invoice_paid("evt_1", CUSTOMER, "in_1", SOON))
    _post(anon_client, subscription("evt_s", "created", CUSTOMER, "active", SOON))

    assert _credits(paying) == 300
    with paying.state.session_factory() as session:
        user = _user(session, "Sam")
        assert user.subscription_status == "active"
        assert user.subscription_period_end == datetime.fromtimestamp(SOON, UTC)


def test_a_failed_renewal_keeps_what_is_left_and_adds_nothing(
    paying: FastAPI, anon_client: TestClient
) -> None:
    _player(paying)
    _post(anon_client, invoice_paid("evt_1", CUSTOMER, "in_1", SOON))

    _post(anon_client, subscription("evt_s", "updated", CUSTOMER, "past_due", SOON))

    assert _credits(paying) == 300
    with paying.state.session_factory() as session:
        assert _user(session, "Sam").subscription_status == "past_due"


def test_an_ended_subscription_takes_its_allowance_but_not_top_ups(
    paying: FastAPI, anon_client: TestClient
) -> None:
    _player(paying)
    _post(anon_client, top_up_completed("evt_t", _user_id(paying), CUSTOMER))
    _post(anon_client, invoice_paid("evt_1", CUSTOMER, "in_1", SOON))
    assert _credits(paying) == 450

    _post(anon_client, subscription("evt_d", "deleted", CUSTOMER, "canceled", SOON))

    assert _credits(paying) == 150


def test_an_allowance_expires_when_its_period_has_ended(paying: FastAPI) -> None:
    client = _player(paying)
    past = datetime.now(UTC) - timedelta(minutes=1)
    with paying.state.session_factory() as session:
        user = _user(session, "Sam")
        start = past - timedelta(days=30)
        grant_allowance(session, user, 300 * CREDIT, "stripe:in_old", past, start)
        session.commit()

    body = client.get("/api/billing").json()

    assert body["credits"] == 0
    assert body["out"] is True


def test_refunds_take_back_credits_by_the_share_refunded_even_below_zero(
    paying: FastAPI, anon_client: TestClient
) -> None:
    client = _player(paying)
    user_id = _user_id(paying)
    _post(anon_client, top_up_completed("evt_t", user_id, CUSTOMER))
    tagged = {"cochess_user": user_id, "product": "top_up"}

    _post(anon_client, charge_refunded("evt_r1", CUSTOMER, 500, 250, tagged))
    assert _credits(paying) == 75
    _post(anon_client, charge_refunded("evt_r1", CUSTOMER, 500, 250, tagged))  # resent
    assert _credits(paying) == 75

    with paying.state.session_factory() as session:  # the player spends 70 meanwhile
        charge_usage(session, user_id, 1, 70 * CREDIT, datetime.now(UTC))
        session.commit()
    _post(anon_client, charge_refunded("evt_r2", CUSTOMER, 500, 500, tagged))  # the rest

    assert _credits(paying) == -70
    assert client.get("/api/billing").json()["out"] is True


def test_an_event_naming_no_player_is_kept_as_unmatched(
    paying: FastAPI, anon_client: TestClient
) -> None:
    assert _post(anon_client, invoice_paid("evt_1", "cus_stranger", "in_1", SOON)) == 200

    with paying.state.session_factory() as session:
        row = session.scalars(select(BillingEventRow)).one()
    assert (row.outcome, row.user_id) == ("unmatched", None)


def test_metadata_naming_another_player_is_not_trusted_over_the_customer(
    paying: FastAPI, anon_client: TestClient
) -> None:
    _player(paying, "Payer", customer="cus_payer")
    _player(paying, "Other", customer="cus_other")

    _post(anon_client, top_up_completed("evt_1", _user_id(paying, "Other"), "cus_payer"))

    assert (_credits(paying, "Payer"), _credits(paying, "Other")) == (150, 0)
