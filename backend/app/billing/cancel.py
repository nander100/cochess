"""Cancelling a player's live subscription now, before something that must not leave them billed:
the owner revoking access (when ticked) or the player deleting their account (SPEC_V4 §10.2, §11).
If the provider can't do it, nothing else may happen: the caller turns the error into a reply."""

import logging

from app.billing.provider import BillingProvider
from app.db.models import User

logger = logging.getLogger("app.billing")

# Subscription states that still bill.
LIVE = frozenset({"active", "trialing", "past_due", "incomplete"})
PAYMENTS_OFF = "Payments aren't set up, so the subscription can't be cancelled from here."
PROVIDER_FAILED = "Stripe didn't cancel the subscription, so nothing was changed. Try again."


class CancelError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def cancel_live_subscription(provider: BillingProvider | None, user: User) -> bool:
    """Cancel `user`'s subscription if it still bills. True if one was cancelled."""
    customer = user.billing_customer_id
    if user.subscription_status not in LIVE or customer is None:
        return False
    if provider is None:
        raise CancelError(503, PAYMENTS_OFF)
    try:
        provider.cancel_subscriptions(customer)
    except Exception as error:  # any provider failure: change nothing
        kind = type(error).__name__
        logger.warning("cancelling a subscription failed for user %s: %s", user.id, kind)
        raise CancelError(502, PROVIDER_FAILED) from error
    return True
