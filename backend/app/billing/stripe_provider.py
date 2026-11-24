"""Stripe Checkout with Managed Payments (SPEC_V4 §6): Stripe is the merchant of record.

Checkout and the customer portal are Stripe's hosted pages, so card details never reach CoChess.
Webhooks are verified against the endpoint's signing secret, then read as plain JSON into
`BillingEvent`s by `event_from`. Field locations follow API versions from 2025-03-31.basil on: an
invoice names its subscription under `parent.subscription_details`, and a subscription's period
end is on its items.
"""

import json
from datetime import UTC, datetime
from typing import Any

import stripe

from app.billing.provider import BillingEvent, CheckoutStart, InvalidEvent
from app.config import BillingProduct, StripeSettings
from app.db.models import User

SIGNATURE_TOLERANCE_S = 300  # Stripe's default: refuse events signed more than 5 minutes ago


class BillingSetupError(RuntimeError):
    """A product's price isn't in Stripe yet: run `python -m scripts.stripe_setup`."""


class StripeProvider:
    name = "stripe"

    def __init__(self, settings: StripeSettings, client: stripe.StripeClient | None = None):
        self._settings = settings
        self._client = client or stripe.StripeClient(settings.secret_key)
        self._prices: dict[str, str] = {}

    def create_checkout(
        self, user: User, product: str, success_url: str, cancel_url: str
    ) -> CheckoutStart:
        item = self._settings.products[product]
        customer = user.billing_customer_id or self._new_customer(user)
        metadata = {"cochess_user": user.id, "product": product}
        params: dict[str, Any] = {
            "mode": "subscription" if item.recurring else "payment",
            "customer": customer,
            "client_reference_id": user.id,
            "line_items": [{"price": self._price(item), "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata,
            "managed_payments": {"enabled": self._settings.managed_payments},
        }
        # The charge or subscription carries them too, so refunds and renewals find the player.
        if item.recurring:
            params["subscription_data"] = {"metadata": metadata}
        else:
            params["payment_intent_data"] = {"metadata": metadata}
        session = self._client.v1.checkout.sessions.create(params)  # type: ignore[arg-type]
        if not session.url:
            raise BillingSetupError("Stripe returned a Checkout Session without a URL")
        return CheckoutStart(url=session.url, customer_id=customer)

    def create_portal(self, customer_id: str, return_url: str) -> str:
        portal = self._client.v1.billing_portal.sessions.create(
            {"customer": customer_id, "return_url": return_url}
        )
        return str(portal.url)

    def cancel_subscriptions(self, customer_id: str) -> None:
        subscriptions = self._client.v1.subscriptions.list(
            {"customer": customer_id, "status": "all", "limit": 100}
        )
        for subscription in subscriptions.data:
            if subscription.status not in ("canceled", "incomplete_expired"):
                self._client.v1.subscriptions.cancel(subscription.id)

    def parse_event(self, payload: bytes, signature: str) -> BillingEvent:
        secret = self._settings.webhook_secret
        if not secret:
            raise InvalidEvent("STRIPE__WEBHOOK_SECRET isn't set")
        try:
            stripe.WebhookSignature.verify_header(
                payload.decode(), signature, secret, tolerance=SIGNATURE_TOLERANCE_S
            )
            data = json.loads(payload)
            return event_from(data, self._settings)
        except (stripe.SignatureVerificationError, ValueError, KeyError, TypeError) as error:
            raise InvalidEvent(str(error)) from error

    def _new_customer(self, user: User) -> str:
        params: dict[str, Any] = {"name": user.name, "metadata": {"cochess_user": user.id}}
        if user.email:
            params["email"] = user.email
        return str(self._client.v1.customers.create(params).id)  # type: ignore[arg-type]

    def _price(self, item: BillingProduct) -> str:
        if item.lookup_key not in self._prices:
            found = self._client.v1.prices.list(
                {"lookup_keys": [item.lookup_key], "active": True, "limit": 1}
            )
            if not found.data:
                raise BillingSetupError(
                    f"no active Stripe price with lookup key {item.lookup_key}: "
                    "run `python -m scripts.stripe_setup`"
                )
            self._prices[item.lookup_key] = found.data[0].id
        return self._prices[item.lookup_key]


def event_from(data: dict[str, Any], settings: StripeSettings) -> BillingEvent:
    """A verified Stripe event as a `BillingEvent`. Types CoChess doesn't act on become `other`."""
    obj: dict[str, Any] = data["data"]["object"]
    kind_of = str(data["type"])
    base: dict[str, Any] = {"provider": "stripe", "event_id": str(data["id"]), "type": kind_of}
    metadata: dict[str, str] = obj.get("metadata") or {}
    customer = _id(obj.get("customer"))
    monthly = _recurring_product(settings)

    if kind_of == "checkout.session.completed":
        user_id = obj.get("client_reference_id") or metadata.get("cochess_user")
        if obj.get("mode") == "payment" and obj.get("payment_status") == "paid":
            return BillingEvent(
                **base,
                kind="top_up_paid",
                user_id=user_id,
                customer_id=customer,
                product=metadata.get("product"),
                amount_cents=obj.get("amount_total"),
                currency=obj.get("currency"),
                object_id=_payment_source(obj),
            )
        return BillingEvent(**base, kind="other", user_id=user_id, customer_id=customer)

    if kind_of == "invoice.paid":
        parent = obj.get("parent") or {}
        subscription = (parent.get("subscription_details") or {}).get("subscription")
        if not subscription:
            return BillingEvent(**base, kind="other", customer_id=customer)
        lines = (obj.get("lines") or {}).get("data") or []
        ends = [line["period"]["end"] for line in lines if line.get("period")]
        return BillingEvent(
            **base,
            kind="period_paid",
            customer_id=customer,
            product=monthly,
            amount_cents=obj.get("amount_paid"),
            currency=obj.get("currency"),
            period_end=_time(max(ends, default=None)),
            object_id=str(obj["id"]),
        )

    if kind_of in ("customer.subscription.created", "customer.subscription.updated"):
        items = (obj.get("items") or {}).get("data") or []
        ends = [i["current_period_end"] for i in items if i.get("current_period_end")]
        return BillingEvent(
            **base,
            kind="subscription_changed",
            user_id=metadata.get("cochess_user"),
            customer_id=customer,
            status=obj.get("status"),
            period_end=_time(max(ends, default=None)),
            object_id=str(obj["id"]),
        )

    if kind_of == "customer.subscription.deleted":
        return BillingEvent(
            **base,
            kind="subscription_ended",
            user_id=metadata.get("cochess_user"),
            customer_id=customer,
            status="canceled",
            object_id=str(obj["id"]),
        )

    if kind_of == "charge.refunded":
        amount, refunded = int(obj.get("amount") or 0), int(obj.get("amount_refunded") or 0)
        return BillingEvent(
            **base,
            kind="refund",
            user_id=metadata.get("cochess_user"),
            customer_id=customer,
            product=metadata.get("product") or monthly,  # renewals' charges carry no metadata
            amount_cents=-refunded,
            currency=obj.get("currency"),
            refund_fraction=refunded / amount if amount else 0.0,
            object_id=_id(obj.get("payment_intent")) or str(obj["id"]),
        )

    return BillingEvent(**base, kind="other", customer_id=customer)


def _payment_source(session: dict[str, Any]) -> str:
    """A top-up's ledger source: its payment intent, which its refunds name too."""
    return _id(session.get("payment_intent")) or str(session["id"])


def _recurring_product(settings: StripeSettings) -> str | None:
    return next((key for key, item in settings.products.items() if item.recurring), None)


def _id(value: object) -> str | None:
    """A Stripe reference: an id, or an expanded object with one."""
    if isinstance(value, dict):
        return str(value["id"]) if value.get("id") else None
    return str(value) if value else None


def _time(seconds: object) -> datetime | None:
    return datetime.fromtimestamp(seconds, UTC) if isinstance(seconds, int) else None
