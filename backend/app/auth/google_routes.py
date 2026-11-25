"""Google sign-in, sign-up and Connect Google (SPEC_V4 §4, §11).

Start: a single-use state, a nonce and a PKCE verifier. Only their hashes are stored; the verifier
lives in an httpOnly cookie on /api/auth/google, which also ties the round trip to this browser.
Callback: the state must match this browser's cookie before the code is even exchanged; then
Google's ID token is checked (auth/google.py) and the account is found by Google's `sub`, never by
email. A new account goes to the sign-up form (age check, terms) and is created on the waitlist
only when that's done; an under-13 answer deletes everything about the attempt.
"""

import hmac
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session
from app.auth.google import GoogleClient, GoogleError, GoogleIdentity, authorize_url
from app.auth.routes import set_session_cookie
from app.auth.service import (
    hash_token,
    name_key,
    new_token,
    session_user,
    start_session,
    unique_name,
)
from app.config import LegalSettings, Settings
from app.db.models import OAuthState, PendingSignup, TermsAcceptance, User
from app.email.outbox import queue_email
from app.limits import per_address

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("app.auth")

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
Intent = Literal["signin", "connect"]
AgeBand = Literal["13_17", "18_plus"]

SIGNUP_GONE = "Your sign-up took too long. Please continue with Google again."
TOO_YOUNG = "Sorry, you can't create a CoChess account yet."
TERMS_NEEDED = "Please accept the terms and privacy policy to continue."
TERMS_CHANGED = "The terms changed since you opened this page. Please read them again."
ALREADY_SIGNED_UP = "This Google account already has a CoChess account. Sign in again."


class SignupInfo(BaseModel):
    name: str
    email: str
    terms_version: str


class SignupRequest(BaseModel):
    birth_year: int
    accept_terms: bool
    terms_version: str = Field(max_length=40)


def age_band(birth_year: int, this_year: int, legal: LegalSettings) -> AgeBand | None:
    """With only a birth year, someone born `min_age` years ago may still be `min_age - 1`, so the
    check errs young: None (too young) unless they're surely `min_age`, and 13_17 unless surely
    18 (SPEC_V4 §11)."""
    years = this_year - birth_year
    if years <= legal.min_age:
        return None
    return "13_17" if years <= legal.adult_age else "18_plus"


def get_google_client(request: Request) -> GoogleClient:
    """One client per app (it caches Google's keys); tests put a fake one in app.state."""
    client: GoogleClient | None = getattr(request.app.state, "google_client", None)
    if client is None:
        client = GoogleClient(request.app.state.settings.google)
        request.app.state.google_client = client
    return client


GoogleDep = Annotated[GoogleClient, Depends(get_google_client)]


@router.get(
    "/google/start",
    dependencies=[Depends(per_address("login", lambda limits: limits.logins_per_minute))],
)
def google_start(
    request: Request, session: SessionDep, settings: SettingsDep, intent: Intent = "signin"
) -> RedirectResponse:
    google = settings.google
    if not google.enabled:
        return _redirect("/?signin=unavailable")
    if intent == "signin" and request.cookies.get(google.age_block_cookie):
        return _redirect("/?signin=age")
    now = datetime.now(UTC)
    user_id = None
    if intent == "connect":
        user = _active_player(request, session, settings, now)
        if user is None:
            return _redirect("/?signin=failed")
        user_id = user.id
    _forget_expired(session, now)
    # An 86-character PKCE verifier (RFC 7636 allows 43 to 128).
    verifier, state, nonce = new_token() + new_token(), new_token(), new_token()
    session.add(
        OAuthState(
            state_hash=hash_token(state),
            browser_hash=hash_token(verifier),
            nonce_hash=hash_token(nonce),
            intent=intent,
            user_id=user_id,
            expires_at=now + timedelta(minutes=google.state_ttl_minutes),
            created_at=now,
        )
    )
    session.commit()
    url = authorize_url(
        google, _callback_url(settings), state=state, nonce=nonce, verifier=verifier
    )
    response = _redirect(url)
    response.set_cookie(
        google.oauth_cookie,
        verifier,
        max_age=google.state_ttl_minutes * 60,
        path="/api/auth/google",
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite="lax",
    )
    return response


@router.get(
    "/google/callback",
    dependencies=[Depends(per_address("login", lambda limits: limits.logins_per_minute))],
)
def google_callback(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    google: GoogleDep,
    state: str = "",
    code: str = "",
    error: str = "",
) -> RedirectResponse:
    now = datetime.now(UTC)
    verifier = request.cookies.get(settings.google.oauth_cookie, "")
    row = _bound_state(session, state, verifier)
    if row is None:
        response = _redirect("/?signin=failed")
    elif row.expires_at <= now:
        response = _redirect("/?signin=expired")
    elif error or not code:
        response = _redirect("/?signin=cancelled" if error else "/?signin=failed")
    else:
        try:
            identity = google.identity(code, verifier, _callback_url(settings), row.nonce_hash)
        except GoogleError as failure:
            log.info("google sign-in refused: %s", failure.reason)
            reason = "unverified" if failure.reason == "unverified_email" else "failed"
            response = _redirect(f"/?signin={reason}")
        else:
            if row.intent == "connect":
                response = _redirect(_connect(session, row.user_id, identity))
            else:
                response = _sign_in(session, settings, identity, now)
    response.delete_cookie(settings.google.oauth_cookie, path="/api/auth/google")
    return response


@router.get("/signup")
def signup_info(request: Request, session: SessionDep, settings: SettingsDep) -> SignupInfo:
    pending = _pending(request, session, settings)
    return SignupInfo(
        name=pending.name, email=pending.email, terms_version=settings.legal.terms_version
    )


@router.post(
    "/signup",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(per_address("login", lambda limits: limits.logins_per_minute))],
)
def sign_up(
    body: SignupRequest, request: Request, session: SessionDep, settings: SettingsDep
) -> Response:
    pending = _pending(request, session, settings)
    now = datetime.now(UTC)
    if not 1900 <= body.birth_year <= now.year:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Check the year.")
    band = age_band(body.birth_year, now.year, settings.legal)
    if band is None:
        return _too_young(session, pending, settings)
    if not body.accept_terms:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=TERMS_NEEDED)
    if body.terms_version != settings.legal.terms_version:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=TERMS_CHANGED)
    name = unique_name(session, pending.name)
    user = User(
        name=name,
        name_key=name_key(name),
        email=pending.email,
        google_sub=pending.google_sub,
        status="waitlisted",
        age_band=band,
        age_checked_at=now,
        waitlisted_at=now,
    )
    session.add(user)
    session.flush()
    session.add(TermsAcceptance(user_id=user.id, version=body.terms_version, accepted_at=now))
    queue_email(session, user, "waitlist_joined", f"waitlist_joined:{user.id}", now=now)
    session.delete(pending)
    token = start_session(session, user, now, settings.auth)
    try:
        session.commit()
    except IntegrityError as clash:  # the same Google account finished signing up twice
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=ALREADY_SIGNED_UP) from clash
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookie(response, token, settings)
    response.delete_cookie(settings.google.signup_cookie, path="/api/auth")
    return response


def _sign_in(
    session: Session, settings: Settings, identity: GoogleIdentity, now: datetime
) -> RedirectResponse:
    user = session.scalars(select(User).where(User.google_sub == identity.sub)).first()
    if user is not None:
        if user.status == "deleted":
            return _redirect("/?signin=failed")
        user.email = identity.email  # Google's current verified address
        token = start_session(session, user, now, settings.auth)
        session.commit()
        response = _redirect("/")
        set_session_cookie(response, token, settings)
        return response
    raw = new_token()
    session.add(
        PendingSignup(
            token_hash=hash_token(raw),
            google_sub=identity.sub,
            email=identity.email,
            name=identity.name,
            expires_at=now + timedelta(minutes=settings.google.signup_ttl_minutes),
            created_at=now,
        )
    )
    session.commit()
    response = _redirect("/signup")
    response.set_cookie(
        settings.google.signup_cookie,
        raw,
        max_age=settings.google.signup_ttl_minutes * 60,
        path="/api/auth",
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite="lax",
    )
    return response


def _connect(session: Session, user_id: str | None, identity: GoogleIdentity) -> str:
    user = session.get(User, user_id) if user_id else None
    if user is None or user.status != "active":
        return "/profile?google=failed"
    if user.google_sub == identity.sub:
        return "/profile?google=connected"
    if user.google_sub is not None:
        return "/profile?google=already"
    taken = session.scalars(select(User.id).where(User.google_sub == identity.sub)).first()
    if taken is not None:
        return "/profile?google=taken"
    user.google_sub, user.email = identity.sub, identity.email
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return "/profile?google=taken"
    return "/profile?google=connected"


def _too_young(session: Session, pending: PendingSignup, settings: Settings) -> Response:
    """Nothing about the attempt is kept (SPEC_V4 §11), and sign-up stays closed in this browser
    for a while, so a different year can't be tried straight away."""
    session.delete(pending)
    session.commit()
    response = JSONResponse({"detail": TOO_YOUNG}, status_code=status.HTTP_403_FORBIDDEN)
    response.delete_cookie(settings.google.signup_cookie, path="/api/auth")
    response.set_cookie(
        settings.google.age_block_cookie,
        "1",
        max_age=settings.legal.age_block_hours * 3600,
        path="/",
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite="lax",
    )
    return response


def _bound_state(session: Session, state: str, verifier: str) -> OAuthState | None:
    """The state row, used up, if this browser started it; otherwise None (and nothing used)."""
    if not state or not verifier:
        return None
    query = select(OAuthState).where(OAuthState.state_hash == hash_token(state))
    found = session.scalars(query).first()
    if found is None or not hmac.compare_digest(found.browser_hash, hash_token(verifier)):
        return None
    session.delete(found)
    session.commit()
    return found


def _pending(request: Request, session: Session, settings: Settings) -> PendingSignup:
    raw = request.cookies.get(settings.google.signup_cookie)
    pending = None
    if raw:
        query = select(PendingSignup).where(PendingSignup.token_hash == hash_token(raw))
        pending = session.scalars(query).first()
    if pending is None or pending.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, detail=SIGNUP_GONE)
    return pending


def _active_player(
    request: Request, session: Session, settings: Settings, now: datetime
) -> User | None:
    token = request.cookies.get(settings.auth.cookie_name)
    user = session_user(session, token, now) if token else None
    return user if user is not None and user.status == "active" else None


def _forget_expired(session: Session, now: datetime) -> None:
    session.execute(delete(OAuthState).where(OAuthState.expires_at <= now))
    session.execute(delete(PendingSignup).where(PendingSignup.expires_at <= now))


def _callback_url(settings: Settings) -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/auth/google/callback"


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
