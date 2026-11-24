"""Stripe without Stripe (CLAUDE.md: never call Stripe in tests). `FakeStripeClient` stands in for
`stripe.StripeClient` and records what was asked of it; events are built here and signed with a
test secret the way Stripe signs them, so the real signature check and parser run on them."""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import stripe
from fastapi import FastAPI

from app.billing.stripe_provider import StripeProvider
from app.config import StripeSettings

WEBHOOK_SECRET = "whsec_test_not_a_real_secret"
TEST_STRIPE = StripeSettings(secret_key="sk_test_fake", webhook_secret=WEBHOOK_SECRET)


@dataclass
class _Resource:
    """One Stripe resource: `create`, `list` and `cancel` record their params."""

    name: str
    calls: list[tuple[str, Any]]
    url_prefix: str = "https://stripe.test"
    listed: list[Any] = field(default_factory=list)
    made: int = 0

    def create(self, params: dict[str, Any]) -> SimpleNamespace:
        self.calls.append((f"{self.name}.create", params))
        self.made += 1
        prefix = {"customers": "cus", "checkout": "cs", "portal": "bps"}[self.name]
        url = f"{self.url_prefix}/{self.name}/{self.made}"
        return SimpleNamespace(id=f"{prefix}_test_{self.made}", url=url)

    def list(self, params: dict[str, Any]) -> SimpleNamespace:
        self.calls.append((f"{self.name}.list", params))
        return SimpleNamespace(data=self.listed)

    def cancel(self, object_id: str) -> None:
        self.calls.append((f"{self.name}.cancel", object_id))


class FakeStripeClient:
    def __init__(
        self, prices: dict[str, str] | None = None, url_prefix: str = "https://stripe.test"
    ) -> None:
        self.calls: list[tuple[str, Any]] = []
        default = {"cochess_monthly_300": "price_monthly", "cochess_top_up_150": "price_top_up"}
        self._prices = default if prices is None else prices
        self.customers = _Resource("customers", self.calls)
        self.subscriptions = _Resource("subscriptions", self.calls)
        self.v1 = SimpleNamespace(
            customers=self.customers,
            prices=SimpleNamespace(list=self._list_prices),
            subscriptions=self.subscriptions,
            checkout=SimpleNamespace(sessions=_Resource("checkout", self.calls, url_prefix)),
            billing_portal=SimpleNamespace(sessions=_Resource("portal", self.calls, url_prefix)),
        )

    def _list_prices(self, params: dict[str, Any]) -> SimpleNamespace:
        self.calls.append(("prices.list", params))
        found = [self._prices[key] for key in params["lookup_keys"] if key in self._prices]
        return SimpleNamespace(data=[SimpleNamespace(id=price) for price in found])

    def params(self, call: str) -> list[Any]:
        return [params for name, params in self.calls if name == call]


def fake_provider(client: FakeStripeClient | None = None) -> StripeProvider:
    fake = client or FakeStripeClient()
    return StripeProvider(TEST_STRIPE, client=cast(stripe.StripeClient, fake))


def install(app: FastAPI, client: FakeStripeClient | None = None) -> FakeStripeClient:
    """Payments on for `app`, against a fake Stripe. Returns the fake to inspect."""
    fake = client or FakeStripeClient()
    app.state.billing_provider = fake_provider(fake)
    return fake


def sign(payload: bytes, secret: str = WEBHOOK_SECRET, at: int | None = None) -> str:
    """A `Stripe-Signature` header the way Stripe computes it."""
    timestamp = int(time.time()) if at is None else at
    signed = f"{timestamp}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def event(event_id: str, kind: str, obj: dict[str, Any]) -> bytes:
    body = {"id": event_id, "object": "event", "type": kind, "data": {"object": obj}}
    return json.dumps(body).encode()


def top_up_completed(event_id: str, user_id: str, customer: str, intent: str = "pi_1") -> bytes:
    return event(
        event_id,
        "checkout.session.completed",
        {
            "id": f"cs_{event_id}",
            "object": "checkout.session",
            "mode": "payment",
            "payment_status": "paid",
            "client_reference_id": user_id,
            "customer": customer,
            "payment_intent": intent,
            "amount_total": 500,
            "currency": "usd",
            "metadata": {"cochess_user": user_id, "product": "top_up"},
        },
    )


def invoice_paid(event_id: str, customer: str, invoice: str, period_end: int) -> bytes:
    return event(
        event_id,
        "invoice.paid",
        {
            "id": invoice,
            "object": "invoice",
            "customer": customer,
            "amount_paid": 1000,
            "currency": "usd",
            "parent": {
                "type": "subscription_details",
                "subscription_details": {"subscription": "sub_1", "metadata": {}},
            },
            "lines": {"data": [{"period": {"start": period_end - 2_592_000, "end": period_end}}]},
        },
    )


def subscription(event_id: str, kind: str, customer: str, status: str, period_end: int) -> bytes:
    return event(
        event_id,
        f"customer.subscription.{kind}",
        {
            "id": "sub_1",
            "object": "subscription",
            "customer": customer,
            "status": status,
            "metadata": {},
            "items": {"data": [{"id": "si_1", "current_period_end": period_end}]},
        },
    )


def charge_refunded(
    event_id: str, customer: str, amount: int, refunded: int, metadata: dict[str, str]
) -> bytes:
    return event(
        event_id,
        "charge.refunded",
        {
            "id": "ch_1",
            "object": "charge",
            "customer": customer,
            "payment_intent": "pi_1",
            "amount": amount,
            "amount_refunded": refunded,
            "currency": "usd",
            "metadata": metadata,
        },
    )
