"""Login routes (SPEC_V2 §11): redeem an invite link, log out."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session
from app.auth.service import InvalidInviteError, end_session, redeem_invite
from app.config import Settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

INVALID_LINK = "This login link has expired or was already used. Ask the owner for a new one."


class RedeemRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)


@router.post("/redeem", status_code=status.HTTP_204_NO_CONTENT)
def redeem(
    body: RedeemRequest, response: Response, session: SessionDep, settings: SettingsDep
) -> None:
    try:
        token = redeem_invite(session, body.token, datetime.now(UTC), settings.auth)
    except InvalidInviteError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK) from error
    response.set_cookie(
        settings.auth.cookie_name,
        token,
        max_age=settings.auth.session_ttl_days * 24 * 60 * 60,
        path="/",
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite="lax",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request, response: Response, session: SessionDep, settings: SettingsDep
) -> None:
    token = request.cookies.get(settings.auth.cookie_name)
    if token:
        end_session(session, token)
    response.delete_cookie(
        settings.auth.cookie_name,
        path="/",
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite="lax",
    )
