"""The Stripe provider (SPEC_V4 §6): what Checkout is asked for, the webhook signature check, and
how each Stripe event reads as a `BillingEvent` (API versions from 2025-03-31.basil on)."""

import json
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.auth.service import create_user
from app.billing.provider import BillingEvent, InvalidEvent
from app.billing.stripe_provider import BillingSetupError, StripeProvider, event_from
from app.config import StripeSettings
from tests.billing_fakes import (
    FakeStripeClient,
    charge_refunded,
    event,
    fake_provider,
    invoice_paid,
    sign,
    subscription,
    top_up_completed,
)

PERIOD_END = 1_767_225_600  # 2026-01-01 00:00 UTC


def _parsed(payload: bytes) -> BillingEvent:
    return event_from(json.loads(payload), StripeSettings())


# Checkout


def test_a_top_up_checkout_is_a_managed_payment_naming_the_player(db_session: Session) -> None:
    user = create_user(db_session, "Sam")
    user.email = "sam@example.test"
    fake = FakeStripeClient()

    start = fake_provider(fake).create_checkout(user, "top_up", "https://x/ok", "https://x/no")

    [customer] = fake.params("customers.create")
    assert customer["metadata"] == {"cochess_user": user.id}
    [params] = fake.params("checkout.create")
    assert params["mode"] == "payment"
    assert params["managed_payments"] == {"enabled": True}
    assert params["customer"] == start.customer_id == "cus_test_1"
    assert params["client_reference_id"] == user.id
    assert params["line_items"] == [{"price": "price_top_up", "quantity": 1}]
    tagged = {"cochess_user": user.id, "product": "top_up"}
    assert params["payment_intent_data"]["metadata"] == tagged
    assert start.url.startswith("https://stripe.test/")


def test_a_subscription_checkout_reuses_the_customer_and_tags_the_subscription(
    db_session: Session,
) -> None:
    user = create_user(db_session, "Sam")
    user.billing_customer_id = "cus_known"
    fake = FakeStripeClient()

    fake_provider(fake).create_checkout(user, "monthly", "https://x/ok", "https://x/no")

    assert fake.params("customers.create") == []
    [params] = fake.params("checkout.create")
    assert params["mode"] == "subscription"
    assert params["customer"] == "cus_known"
    assert params["subscription_data"]["metadata"]["product"] == "monthly"
    assert "payment_intent_data" not in params


def test_checkout_fails_clearly_when_the_price_isnt_set_up(db_session: Session) -> None:
    user = create_user(db_session, "Sam")

    with pytest.raises(BillingSetupError, match="stripe_setup"):
        fake_provider(FakeStripeClient(prices={})).create_checkout(user, "monthly", "a", "b")


# Signatures


def test_a_correctly_signed_event_is_read() -> None:
    payload = invoice_paid("evt_1", "cus_1", "in_1", PERIOD_END)

    parsed = fake_provider().parse_event(payload, sign(payload))

    assert parsed.kind == "period_paid"


@pytest.mark.parametrize(
    "header",
    [
        "",
        "t=1,v1=deadbeef",
        sign(b"something else"),
        sign(invoice_paid("evt_1", "cus_1", "in_1", PERIOD_END), secret="whsec_wrong"),
        sign(invoice_paid("evt_1", "cus_1", "in_1", PERIOD_END), at=int(time.time()) - 3600),
    ],
    ids=["missing", "garbage", "other-body", "wrong-secret", "too-old"],
)
def test_a_badly_signed_event_is_refused(header: str) -> None:
    payload = invoice_paid("evt_1", "cus_1", "in_1", PERIOD_END)

    with pytest.raises(InvalidEvent):
        fake_provider().parse_event(payload, header)


def test_events_are_refused_while_no_webhook_secret_is_set() -> None:
    payload = invoice_paid("evt_1", "cus_1", "in_1", PERIOD_END)
    provider = StripeProvider(StripeSettings(secret_key="sk_test_fake"), client=None)

    with pytest.raises(InvalidEvent, match="WEBHOOK_SECRET"):
        provider.parse_event(payload, sign(payload))


def test_a_signed_body_that_isnt_an_event_is_refused() -> None:
    payload = b'{"id": "evt_1"}'

    with pytest.raises(InvalidEvent):
        fake_provider().parse_event(payload, sign(payload))


# Reading events


def test_a_paid_top_up_checkout_reads_as_a_top_up() -> None:
    parsed = _parsed(top_up_completed("evt_1", "user-1", "cus_1", intent="pi_9"))

    assert parsed.kind == "top_up_paid"
    assert (parsed.user_id, parsed.customer_id) == ("user-1", "cus_1")
    assert (parsed.product, parsed.amount_cents, parsed.currency) == ("top_up", 500, "usd")
    assert parsed.object_id == "pi_9"


def test_an_unpaid_checkout_is_not_a_top_up() -> None:
    body = json.loads(top_up_completed("evt_1", "user-1", "cus_1"))
    body["data"]["object"]["payment_status"] = "unpaid"

    assert event_from(body, StripeSettings()).kind == "other"


def test_a_subscription_invoice_reads_as_a_paid_period_ending_with_its_lines() -> None:
    parsed = _parsed(invoice_paid("evt_1", "cus_1", "in_1", PERIOD_END))

    assert parsed.kind == "period_paid"
    assert parsed.product == "monthly"
    assert parsed.object_id == "in_1"
    assert parsed.period_end == datetime(2026, 1, 1, tzinfo=UTC)


def test_an_invoice_without_a_subscription_is_ignored() -> None:
    body = json.loads(invoice_paid("evt_1", "cus_1", "in_1", PERIOD_END))
    body["data"]["object"]["parent"] = None

    assert event_from(body, StripeSettings()).kind == "other"


def test_subscription_events_carry_status_and_the_items_period_end() -> None:
    changed = _parsed(subscription("evt_1", "updated", "cus_1", "past_due", PERIOD_END))
    ended = _parsed(subscription("evt_2", "deleted", "cus_1", "canceled", PERIOD_END))

    assert (changed.kind, changed.status) == ("subscription_changed", "past_due")
    assert changed.period_end == datetime(2026, 1, 1, tzinfo=UTC)
    assert (ended.kind, ended.status) == ("subscription_ended", "canceled")


def test_a_refund_reads_as_the_share_refunded_so_far() -> None:
    parsed = _parsed(charge_refunded("evt_1", "cus_1", 500, 250, {"product": "top_up"}))

    assert parsed.kind == "refund"
    assert parsed.refund_fraction == 0.5
    assert parsed.amount_cents == -250
    assert parsed.object_id == "pi_1"


def test_a_renewal_refund_without_metadata_is_the_subscriptions() -> None:
    parsed = _parsed(charge_refunded("evt_1", "cus_1", 1000, 1000, {}))

    assert parsed.product == "monthly"


def test_other_events_are_kept_but_do_nothing() -> None:
    assert _parsed(event("evt_1", "customer.created", {"id": "cus_1"})).kind == "other"
