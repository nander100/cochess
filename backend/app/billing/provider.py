"""The payment provider behind one interface (SPEC_V4 §6): Stripe Managed Payments now, possibly
another later. Nothing outside the provider's own module names it; webhooks arrive here as
`BillingEvent`s, so the credit rules (app/billing/webhooks.py) never see a provider's objects."""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.db.models import User

EventKind = Literal[
    "top_up_paid",  # a one-time purchase was paid: add its credits
    "period_paid",  # a subscription period was paid: its allowance, until `period_end`
    "subscription_changed",  # status or period end changed
    "subscription_ended",  # cancelled for good: what's left of the allowance goes
    "refund",  # money went back: so do its credits (`refund_fraction` of the product's)
    "other",  # stored and acknowledged, nothing to do
]


class InvalidEvent(Exception):
    """The webhook's signature or body doesn't check out: refuse it (400)."""


class BillingEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    event_id: str
    type: str  # the provider's own event type, kept for the record
    kind: EventKind
    user_id: str | None = None  # ours, when the provider was told it (checkout, metadata)
    customer_id: str | None = None  # the provider's customer
    product: str | None = None  # a key of `StripeSettings.products`
    amount_cents: int | None = None  # money in; negative for a refund
    currency: str | None = None
    period_end: datetime | None = None
    status: str | None = None  # subscription status, as the provider says it
    refund_fraction: float | None = None  # of the original payment, so far in total
    object_id: str | None = None  # the paid or refunded thing: the ledger's source


class CheckoutStart(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str  # where the browser goes to pay
    customer_id: str  # the provider's customer for this player (made on first checkout)


class BillingProvider(Protocol):
    name: str

    def create_checkout(
        self, user: User, product: str, success_url: str, cancel_url: str
    ) -> CheckoutStart: ...

    def create_portal(self, customer_id: str, return_url: str) -> str: ...

    def parse_event(self, payload: bytes, signature: str) -> BillingEvent: ...

    def cancel_subscriptions(self, customer_id: str) -> None: ...
