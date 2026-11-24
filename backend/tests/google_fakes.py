"""A fake Google for tests (SPEC_V4 §14.3): its token and certificate endpoints over
httpx.MockTransport, signing ID tokens with a key made in memory. Tests never call Google."""

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt, jwt

from app.config import GoogleSettings

CLIENT_ID = "test-client.apps.googleusercontent.com"
CLIENT_SECRET = "test-secret"
SETTINGS = GoogleSettings(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)


def _key_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


@dataclass
class FakeGoogle:
    """Register what Google answers for a code with `will_return`, then pass `transport()`."""

    kid: str = "key-1"
    certs_requests: int = 0
    token_requests: list[dict[str, str]] = field(default_factory=list)
    _codes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._private, self.public_pem = _key_pair()

    def id_token(self, *, signing_key: str | None = None, **overrides: Any) -> str:
        """A signed ID token with sensible claims; `overrides` replace them, or drop them (None)."""
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "sub": "1001",
            "email": "player@example.com",
            "email_verified": True,
            "name": "Sam Player",
            "nonce": "nonce-1",
            "iat": now,
            "exp": now + 300,
        }
        claims.update(overrides)
        signer = crypt.RSASigner.from_string(signing_key or self._private, self.kid)
        payload = {key: value for key, value in claims.items() if value is not None}
        return jwt.encode(signer, payload).decode()

    def other_key_token(self, **overrides: Any) -> str:
        """Signed by a key Google doesn't publish (same kid): the signature check must fail."""
        private, _ = _key_pair()
        return self.id_token(signing_key=private, **overrides)

    def will_return(self, code: str, id_token: str) -> None:
        self._codes[code] = id_token

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url == httpx.URL(SETTINGS.certs_url):
            self.certs_requests += 1
            return httpx.Response(200, json={self.kid: self.public_pem})
        if request.url == httpx.URL(SETTINGS.token_url) and request.method == "POST":
            form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
            self.token_requests.append(form)
            token = self._codes.get(form.get("code", ""))
            if token is None:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"id_token": token, "access_token": "unused"})
        return httpx.Response(404)
