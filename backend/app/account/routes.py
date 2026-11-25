"""A player's own account (SPEC_V4 §11): export everything that's theirs, or delete the account.
Any signed-in account may use them, including a waitlisted or paused one."""

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.account.deletion import delete_account
from app.account.export import build_export
from app.api.deps import get_app_settings, get_session
from app.auth.deps import CurrentAccount
from app.billing.cancel import CancelError, cancel_live_subscription
from app.billing.provider import BillingProvider
from app.config import Settings
from app.limits import DAY, check

router = APIRouter(prefix="/api/me", tags=["account"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

WRONG_NAME = "To delete your account, type your name exactly as it appears on your profile."
TOO_OFTEN = "You've downloaded your data several times today. Please try again tomorrow."
OWNER = "The owner's account can't be deleted here. Make another account the owner first (CLI)."


class DeleteRequest(BaseModel):
    confirm_name: str = Field(max_length=100)


@router.post("/export")
def export(
    request: Request, user: CurrentAccount, session: SessionDep, settings: SettingsDep
) -> Response:
    """Everything that's the player's, as one zip download."""
    check(session, f"export:{user.id}", settings.rate_limits.exports_per_day, DAY, TOO_OFTEN)
    now = datetime.now(UTC)
    data = build_export(session, user, settings, now)
    filename = f"cochess-export-{now:%Y-%m-%d}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    body: DeleteRequest,
    request: Request,
    response: Response,
    user: CurrentAccount,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    """Delete the account for good (SPEC_V4 §11): a live subscription is cancelled first (if
    Stripe can't, nothing is deleted), then everything goes in one transaction and the session
    ends."""
    if body.confirm_name.strip().casefold() != user.name.casefold():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=WRONG_NAME)
    if user.role == "owner":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=OWNER)
    provider = cast(BillingProvider | None, request.app.state.billing_provider)
    try:
        cancel_live_subscription(provider, user)
    except CancelError as error:
        raise HTTPException(error.status, detail=error.message) from error
    delete_account(session, user, datetime.now(UTC))
    session.commit()
    response.delete_cookie(settings.auth.cookie_name, path="/", httponly=True)
