"""Paying (SPEC_V4 §6.2): start a checkout, open the customer portal, and the provider's webhook,
the only place money becomes credits. Card details never reach CoChess; the browser is never
trusted for what was paid (prices come from config, credits from verified webhooks)."""

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session
from app.auth.deps import CurrentUser
from app.billing.provider import BillingProvider, InvalidEvent
from app.billing.webhooks import apply_event
from app.config import Settings

logger = logging.getLogger("app.billing")

router = APIRouter(prefix="/api/billing", tags=["billing"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

PAYMENTS_OFF = "Payments aren't set up yet. Please try again later."
PROVIDER_FAILED = "The payment page couldn't be opened. Please try again in a moment."
ALREADY_SUBSCRIBED = "You already have a subscription. Manage it from your profile."
NO_CUSTOMER = "There's no subscription or purchase to manage yet."
# A subscription in these states still bills, so a second one would charge twice.
LIVE_STATUSES = frozenset({"active", "trialing", "past_due", "incomplete"})


def get_billing_provider(request: Request) -> BillingProvider:
    provider = cast(BillingProvider | None, request.app.state.billing_provider)
    if provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=PAYMENTS_OFF)
    return provider


ProviderDep = Annotated[BillingProvider, Depends(get_billing_provider)]


class CheckoutRequest(BaseModel):
    product: Literal["monthly", "top_up"]


class RedirectUrl(BaseModel):
    url: str


class Received(BaseModel):
    received: bool


@router.post("/checkout")
def start_checkout(
    body: CheckoutRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    provider: ProviderDep,
) -> RedirectUrl:
    item = settings.stripe.products[body.product]
    if item.recurring and user.subscription_status in LIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=ALREADY_SUBSCRIBED)
    base = settings.public_base_url.rstrip("/")
    try:
        start = provider.create_checkout(
            user,
            body.product,
            success_url=f"{base}/billing/return?product={body.product}",
            cancel_url=f"{base}/profile",
        )
    except Exception:
        logger.exception("checkout for user %s failed", user.id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=PROVIDER_FAILED) from None
    if user.billing_customer_id is None:
        user.billing_customer_id = start.customer_id
        user.billing_provider = provider.name
        session.commit()
    return RedirectUrl(url=start.url)


@router.post("/portal")
def open_portal(user: CurrentUser, settings: SettingsDep, provider: ProviderDep) -> RedirectUrl:
    if user.billing_customer_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=NO_CUSTOMER)
    try:
        url = provider.create_portal(
            user.billing_customer_id, return_url=f"{settings.public_base_url.rstrip('/')}/profile"
        )
    except Exception:
        logger.exception("portal for user %s failed", user.id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=PROVIDER_FAILED) from None
    return RedirectUrl(url=url)


@router.post("/webhook")
async def webhook(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    provider: ProviderDep,
    stripe_signature: Annotated[str, Header()] = "",
) -> Received:
    """No session: the signature on the raw body is the check. A refused signature is 400; a
    failure while applying is 500, so the provider sends the event again."""
    payload = await request.body()
    try:
        event = provider.parse_event(payload, stripe_signature)
    except InvalidEvent as error:
        logger.warning("refused a billing webhook: %s", error)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid event") from None
    try:
        apply_event(session, event, settings, datetime.now(UTC))
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("billing event %s failed", event.event_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="retry") from None
    return Received(received=True)
