"""Create CoChess's products and prices in Stripe (SPEC_V4 §6.1), found later by lookup key, so
no price id goes in config. Safe to run again: a lookup key that already has an active price is
left alone (change a price by giving it a new lookup key in config).

Usage (from backend/, with STRIPE__SECRET_KEY in .env):
    uv run python -m scripts.stripe_setup            # test mode only
    uv run python -m scripts.stripe_setup --live     # the live account, on purpose
"""

import argparse
import sys
from typing import Any

import stripe

from app.config import BillingProduct, Settings

TEST_PREFIXES = ("sk_test_", "rk_test_")


def ensure_price(client: stripe.StripeClient, item: BillingProduct, tax_code: str) -> str:
    """The active price for `item`'s lookup key, made (with its product) if there isn't one."""
    found = client.v1.prices.list({"lookup_keys": [item.lookup_key], "active": True, "limit": 1})
    if found.data:
        return f"{item.lookup_key}: already there ({found.data[0].id})"
    product = client.v1.products.create({"name": item.name, "tax_code": tax_code})
    params: dict[str, Any] = {
        "product": product.id,
        "currency": "usd",
        "unit_amount": item.price_cents,
        "lookup_key": item.lookup_key,
        "tax_behavior": "exclusive",  # prices are before tax; Checkout adds it (SPEC_V4 §6.2)
    }
    if item.recurring:
        params["recurring"] = {"interval": "month"}
    price = client.v1.prices.create(params)  # type: ignore[arg-type]
    return f"{item.lookup_key}: made {price.id} for product {product.id}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="allow a live-mode key")
    args = parser.parse_args()
    settings = Settings().stripe
    if not settings.secret_key:
        sys.exit("STRIPE__SECRET_KEY isn't set.")
    if not settings.secret_key.startswith(TEST_PREFIXES) and not args.live:
        sys.exit("That's not a test-mode key. Pass --live to set up the live account.")
    client = stripe.StripeClient(settings.secret_key)
    for item in settings.products.values():
        print(ensure_price(client, item, settings.tax_code))


if __name__ == "__main__":
    main()
