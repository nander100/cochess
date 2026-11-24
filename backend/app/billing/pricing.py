"""What a coach call costs (SPEC_V4 §5.1): its tokens at the model's prices in config.

Prices are dollars per million tokens, which is microdollars per token, so the cost is a plain sum,
rounded up to whole microdollars so a call is never charged less than it cost.
"""

import logging
import math

from app.coach.client import Usage
from app.config import ModelPrice, PricingSettings

log = logging.getLogger("app.billing")


def cost_microusd(pricing: PricingSettings, model: str, usage: Usage) -> int:
    price = pricing.models.get(model)
    if price is None:
        # Settings refuse unpriced coach models at startup, so this is a model the API answered
        # with that config doesn't name. Charge the highest rates rather than nothing.
        log.warning("no price for model %s; charging the highest rates", model)
        price = _highest(pricing)
    microusd = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_write_tokens * price.cache_write
        + usage.cache_read_tokens * price.cache_read
    )
    return math.ceil(microusd - 1e-9)  # float noise mustn't add a microdollar


def _highest(pricing: PricingSettings) -> ModelPrice:
    prices = list(pricing.models.values())
    return ModelPrice(
        input=max(p.input for p in prices),
        output=max(p.output for p in prices),
        cache_write=max(p.cache_write for p in prices),
        cache_read=max(p.cache_read for p in prices),
    )
