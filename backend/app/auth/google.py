"""Sign in with Google (SPEC_V4 §4.1): the authorization URL, the code exchange, and the ID-token
check. Identity comes only from an ID token verified here, never from the browser.

The token's signature is checked against Google's published keys (cached, refetched when Google
rotates them), then its issuer, audience, expiry, our nonce, and a verified email.
"""

import base64
import hashlib
import hmac
import time
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from google.auth import exceptions as google_errors
from google.auth import jwt
from pydantic import BaseModel, ConfigDict

from app.config import GoogleSettings

Reason = Literal["exchange_failed", "invalid_token", "unverified_email"]
_SCOPES = "openid email profile"
_MAX_NAME_CHARS = 60


class GoogleError(Exception):
    def __init__(self, reason: Reason) -> None:
        super().__init__(reason)
        self.reason: Reason = reason


class GoogleIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    sub: str  # Google's account id: the account key, never the email
    email: str
    name: str


def pkce_challenge(verifier: str) -> str:
    """S256 code challenge (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorize_url(
    settings: GoogleSettings, redirect_uri: str, *, state: str, nonce: str, verifier: str
) -> str:
    query = {
        "client_id": settings.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": pkce_challenge(verifier),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{settings.authorize_url}?{urlencode(query)}"


class GoogleClient:
    """Talks to Google's token and key endpoints. `transport` is a fake in tests."""

    def __init__(self, settings: GoogleSettings, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._http = httpx.Client(transport=transport, timeout=settings.timeout_seconds)
        self._certs: dict[str, str] = {}
        self._certs_fetched = float("-inf")

    def identity(
        self, code: str, verifier: str, redirect_uri: str, nonce_hash: str
    ) -> GoogleIdentity:
        claims = self._claims(self._exchange(code, verifier, redirect_uri))
        nonce = claims.get("nonce")
        if not isinstance(nonce, str) or not hmac.compare_digest(_sha256(nonce), nonce_hash):
            raise GoogleError("invalid_token")
        sub, email = claims.get("sub"), claims.get("email")
        if not isinstance(sub, str) or not sub:
            raise GoogleError("invalid_token")
        verified = claims.get("email_verified") in (True, "true")
        if not isinstance(email, str) or not email or not verified:
            raise GoogleError("unverified_email")
        return GoogleIdentity(sub=sub, email=email, name=_name(claims.get("name"), email))

    def _exchange(self, code: str, verifier: str, redirect_uri: str) -> str:
        form = {
            "code": code,
            "code_verifier": verifier,
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        try:
            response = self._http.post(self._settings.token_url, data=form)
        except httpx.HTTPError as error:
            raise GoogleError("exchange_failed") from error
        token = response.json().get("id_token") if response.is_success else None
        if not isinstance(token, str):
            raise GoogleError("exchange_failed")
        return token

    def _claims(self, token: str) -> dict[str, Any]:
        try:
            claims = self._decode(token, refresh=False)
        except _UnknownKey:
            claims = self._decode(token, refresh=True)  # Google may have rotated its keys
        if claims.get("iss") not in self._settings.issuers:
            raise GoogleError("invalid_token")
        return claims

    def _decode(self, token: str, *, refresh: bool) -> dict[str, Any]:
        certs = self._google_certs(refresh)
        try:
            # google-auth ships no type hints for jwt.decode.
            claims: dict[str, Any] = jwt.decode(  # type: ignore[no-untyped-call]
                token, certs=certs, audience=self._settings.client_id
            )
        except google_errors.MalformedError as error:
            if "not found" in str(error) and not refresh:
                raise _UnknownKey from error
            raise GoogleError("invalid_token") from error
        except (ValueError, google_errors.GoogleAuthError) as error:
            raise GoogleError("invalid_token") from error
        return claims

    def _google_certs(self, refresh: bool) -> dict[str, str]:
        stale = time.monotonic() - self._certs_fetched > self._settings.certs_cache_seconds
        if refresh or stale or not self._certs:
            try:
                response = self._http.get(self._settings.certs_url)
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise GoogleError("invalid_token") from error
            self._certs = {str(kid): str(pem) for kid, pem in response.json().items()}
            self._certs_fetched = time.monotonic()
        return self._certs


class _UnknownKey(Exception):
    """The token names a key id missing from the cached keys."""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _name(name: object, email: str) -> str:
    """Google's display name, or the email's local part when there's none."""
    text = name.strip() if isinstance(name, str) else ""
    return (text or email.split("@", 1)[0])[:_MAX_NAME_CHARS]
