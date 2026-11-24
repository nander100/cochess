"""Checking Google's answer (SPEC_V4 §4.1, §14.3): identity only from a verified ID token."""

import time
from urllib.parse import parse_qs, urlsplit

import pytest

from app.auth.google import GoogleClient, GoogleError, GoogleIdentity, authorize_url, pkce_challenge
from app.auth.service import hash_token
from tests.google_fakes import CLIENT_ID, CLIENT_SECRET, SETTINGS, FakeGoogle

REDIRECT = "https://cochess.example/api/auth/google/callback"
VERIFIER = "v" * 64
NONCE_HASH = hash_token("nonce-1")


def _identity(fake: FakeGoogle, token: str, client: GoogleClient | None = None) -> GoogleIdentity:
    fake.will_return("code-1", token)
    client = client or GoogleClient(SETTINGS, fake.transport())
    return client.identity("code-1", VERIFIER, REDIRECT, NONCE_HASH)


def _reason(fake: FakeGoogle, token: str) -> str:
    with pytest.raises(GoogleError) as caught:
        _identity(fake, token)
    return caught.value.reason


def test_a_valid_answer_gives_the_account_and_sends_the_pkce_verifier() -> None:
    fake = FakeGoogle()

    identity = _identity(fake, fake.id_token())

    assert identity == GoogleIdentity(sub="1001", email="player@example.com", name="Sam Player")
    sent = fake.token_requests[0]
    assert sent["code_verifier"] == VERIFIER
    assert (sent["client_id"], sent["client_secret"]) == (CLIENT_ID, CLIENT_SECRET)
    assert (sent["grant_type"], sent["redirect_uri"]) == ("authorization_code", REDIRECT)


@pytest.mark.parametrize(
    ("claims", "reason"),
    [
        ({"aud": "someone-else.apps.googleusercontent.com"}, "invalid_token"),
        ({"iss": "https://evil.example"}, "invalid_token"),
        ({"exp": int(time.time()) - 600, "iat": int(time.time()) - 900}, "invalid_token"),
        ({"nonce": "another-nonce"}, "invalid_token"),
        ({"nonce": None}, "invalid_token"),
        ({"sub": None}, "invalid_token"),
        ({"email_verified": False}, "unverified_email"),
        ({"email": None}, "unverified_email"),
    ],
)
def test_a_bad_answer_is_refused(claims: dict[str, object], reason: str) -> None:
    fake = FakeGoogle()

    assert _reason(fake, fake.id_token(**claims)) == reason


def test_a_token_signed_by_another_key_is_refused() -> None:
    fake = FakeGoogle()

    assert _reason(fake, fake.other_key_token()) == "invalid_token"


def test_a_code_google_refuses_is_an_exchange_failure() -> None:
    fake = FakeGoogle()
    client = GoogleClient(SETTINGS, fake.transport())

    with pytest.raises(GoogleError) as caught:
        client.identity("never-issued", VERIFIER, REDIRECT, NONCE_HASH)

    assert caught.value.reason == "exchange_failed"


def test_googles_keys_are_fetched_once_then_cached() -> None:
    fake = FakeGoogle()
    client = GoogleClient(SETTINGS, fake.transport())

    _identity(fake, fake.id_token(), client)
    _identity(fake, fake.id_token(), client)

    assert fake.certs_requests == 1


def test_keys_are_fetched_again_when_google_rotates_them() -> None:
    fake = FakeGoogle()
    client = GoogleClient(SETTINGS, fake.transport())
    _identity(fake, fake.id_token(), client)

    rotated = FakeGoogle(kid="key-2")
    fake.kid, fake.public_pem = rotated.kid, rotated.public_pem
    fake.will_return("code-1", rotated.id_token())

    assert client.identity("code-1", VERIFIER, REDIRECT, NONCE_HASH).sub == "1001"
    assert fake.certs_requests == 2


def test_the_pkce_challenge_matches_rfc_7636() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    assert pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_the_authorization_url_asks_only_for_sign_in_scopes() -> None:
    url = authorize_url(SETTINGS, REDIRECT, state="s1", nonce="n1", verifier=VERIFIER)

    query = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
    assert url.startswith(SETTINGS.authorize_url + "?")
    assert query["scope"] == "openid email profile"
    assert (query["response_type"], query["state"], query["nonce"]) == ("code", "s1", "n1")
    assert query["code_challenge"] == pkce_challenge(VERIFIER)
    assert query["code_challenge_method"] == "S256"
    assert (query["client_id"], query["redirect_uri"]) == (CLIENT_ID, REDIRECT)
