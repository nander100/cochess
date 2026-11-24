"""Google sign-in, the waitlist and Connect Google through the API (SPEC_V4 §4, §11, §14.3)."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.accounts import admit, suspend
from app.auth.google import GoogleClient
from app.config import Settings
from app.db.models import EmailOutboxRow, OAuthState, PendingSignup, TermsAcceptance, User
from app.main import create_app
from tests.auth_helpers import BASE_URL, log_in
from tests.databases import fresh_database_url
from tests.google_fakes import SETTINGS as GOOGLE
from tests.google_fakes import FakeGoogle

THIS_YEAR = datetime.now(UTC).year
TERMS = Settings(_env_file=None).legal.terms_version


@pytest.fixture
def fake() -> FakeGoogle:
    return FakeGoogle()


@pytest.fixture
def app(fake: FakeGoogle) -> FastAPI:
    settings = Settings(
        _env_file=None,
        database_url=fresh_database_url(),
        public_base_url="https://cochess.example",
        google=GOOGLE,
    )
    app = create_app(settings)
    app.state.google_client = GoogleClient(GOOGLE, fake.transport())
    return app


@pytest.fixture
def browser(app: FastAPI) -> TestClient:
    return TestClient(app, base_url=BASE_URL)


def _location(response: httpx.Response) -> str:
    assert response.status_code == 303, response.text
    return response.headers["location"]


def _start(browser: TestClient, intent: str = "signin") -> dict[str, str]:
    url = _location(browser.get(f"/api/auth/google/start?intent={intent}", follow_redirects=False))
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def _google_answers(
    browser: TestClient, fake: FakeGoogle, intent: str = "signin", **claims: object
) -> str:
    """Start, let Google answer with these claims, and return where the callback sends us."""
    query = _start(browser, intent)
    fake.will_return("code-1", fake.id_token(nonce=query["nonce"], **claims))
    response = browser.get(
        f"/api/auth/google/callback?code=code-1&state={query['state']}", follow_redirects=False
    )
    return _location(response)


def _sign_up(browser: TestClient, birth_year: int, **extra: object) -> httpx.Response:
    body = {"birth_year": birth_year, "accept_terms": True, "terms_version": TERMS, **extra}
    return browser.post("/api/auth/signup", json=body)


def _users(app: FastAPI) -> list[User]:
    with app.state.session_factory() as session:
        return list(session.scalars(select(User).order_by(User.created_at)))


def _session(app: FastAPI) -> Session:
    session: Session = app.state.session_factory()
    return session


# Starting


def test_start_sends_the_browser_to_google_with_a_bound_cookie(browser: TestClient) -> None:
    response = browser.get("/api/auth/google/start?intent=signin", follow_redirects=False)

    assert _location(response).startswith(GOOGLE.authorize_url + "?")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{GOOGLE.oauth_cookie}=")
    assert "HttpOnly" in cookie and "Secure" in cookie and "Path=/api/auth/google" in cookie


def test_start_without_google_configured_says_so() -> None:
    app = create_app(Settings(_env_file=None, database_url=fresh_database_url()))
    browser = TestClient(app, base_url=BASE_URL)

    response = browser.get("/api/auth/google/start?intent=signin", follow_redirects=False)

    assert _location(response) == "/?signin=unavailable"


# Joining the waitlist


def test_a_new_google_account_goes_to_the_sign_up_form_and_isnt_a_user_yet(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    assert _google_answers(browser, fake) == "/signup"

    info = browser.get("/api/auth/signup")
    assert info.status_code == 200
    assert info.json() == {
        "name": "Sam Player",
        "email": "player@example.com",
        "terms_version": TERMS,
    }
    assert _users(app) == []


def test_signing_up_joins_the_waitlist_and_only_the_status_page_works(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    _google_answers(browser, fake)

    response = _sign_up(browser, THIS_YEAR - 30)

    assert response.status_code == 204, response.text
    [user] = _users(app)
    assert (user.status, user.google_sub, user.email) == (
        "waitlisted",
        "1001",
        "player@example.com",
    )
    assert (user.age_band, user.role) == ("18_plus", "player")
    me = browser.get("/api/me")
    assert me.status_code == 200
    assert me.json()["status"] == "waitlisted" and me.json()["google_connected"] is True
    games = browser.get("/api/games")
    assert games.status_code == 403 and "waiting" in games.json()["detail"]
    with _session(app) as session:
        assert session.scalars(select(PendingSignup)).all() == []
        accepted = session.scalars(select(TermsAcceptance)).one()
        assert (accepted.user_id, accepted.version) == (user.id, TERMS)
        assert session.scalars(select(EmailOutboxRow.kind)).all() == ["waitlist_joined"]


def test_a_13_to_17_year_old_is_banded_without_keeping_the_birth_year(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    _google_answers(browser, fake)

    assert _sign_up(browser, THIS_YEAR - 15).status_code == 204

    [user] = _users(app)
    assert user.age_band == "13_17"


@pytest.mark.parametrize("age", [5, 12, 13])  # born 13 years ago may still be 12: refused
def test_under_13_stores_nothing_and_closes_sign_up_in_that_browser(
    app: FastAPI, browser: TestClient, fake: FakeGoogle, age: int
) -> None:
    _google_answers(browser, fake)

    response = _sign_up(browser, THIS_YEAR - age)

    assert response.status_code == 403
    assert _users(app) == []
    with _session(app) as session:
        assert session.scalars(select(PendingSignup)).all() == []
        assert session.scalars(select(EmailOutboxRow)).all() == []
    again = browser.get("/api/auth/google/start?intent=signin", follow_redirects=False)
    assert _location(again) == "/?signin=age"


def test_the_borderline_18th_year_counts_as_13_to_17(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    _google_answers(browser, fake)

    _sign_up(browser, THIS_YEAR - 18)

    assert _users(app)[0].age_band == "13_17"


@pytest.mark.parametrize(
    "extra", [{"accept_terms": False}, {"terms_version": "an-old-version"}], ids=["no", "old"]
)
def test_the_terms_must_be_accepted_in_their_current_version(
    app: FastAPI, browser: TestClient, fake: FakeGoogle, extra: dict[str, object]
) -> None:
    _google_answers(browser, fake)

    response = _sign_up(browser, THIS_YEAR - 30, **extra)

    assert response.status_code == 422
    assert _users(app) == []
    assert browser.get("/api/auth/signup").status_code == 200  # can still finish


def test_an_impossible_birth_year_is_refused(browser: TestClient, fake: FakeGoogle) -> None:
    _google_answers(browser, fake)

    assert _sign_up(browser, THIS_YEAR + 1).status_code == 422
    assert _sign_up(browser, 1850).status_code == 422


def test_a_sign_up_left_too_long_has_to_start_again(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    _google_answers(browser, fake)
    with _session(app) as session:
        past = datetime.now(UTC) - timedelta(minutes=1)
        session.execute(update(PendingSignup).values(expires_at=past))
        session.commit()

    assert browser.get("/api/auth/signup").status_code == 410
    assert _sign_up(browser, THIS_YEAR - 30).status_code == 410


def test_a_taken_name_gets_a_number(app: FastAPI, browser: TestClient, fake: FakeGoogle) -> None:
    log_in(app, "Sam Player")
    _google_answers(browser, fake)

    _sign_up(browser, THIS_YEAR - 30)

    assert sorted(u.name for u in _users(app)) == ["Sam Player", "Sam Player 2"]


# Signing in


def test_an_accepted_player_signs_in_with_google_and_reaches_the_app(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    _google_answers(browser, fake)
    _sign_up(browser, THIS_YEAR - 30)
    with _session(app) as session:
        admit(session, session.scalars(select(User)).one(), datetime.now(UTC))
        session.commit()

    later = TestClient(app, base_url=BASE_URL)  # another browser, later
    assert _google_answers(later, fake) == "/"
    assert later.get("/api/me").json()["status"] == "active"
    assert later.get("/api/games").status_code == 200


def test_a_paused_player_who_signs_in_sees_only_that_their_access_is_paused(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    _google_answers(browser, fake)
    _sign_up(browser, THIS_YEAR - 30)
    with _session(app) as session:
        user = session.scalars(select(User)).one()
        admit(session, user, datetime.now(UTC))
        suspend(session, user, datetime.now(UTC), reason="check")
        session.commit()

    later = TestClient(app, base_url=BASE_URL)
    assert _google_answers(later, fake) == "/"
    assert later.get("/api/me").json()["status"] == "suspended"
    games = later.get("/api/games")
    assert games.status_code == 403 and "paused" in games.json()["detail"]


def test_a_changed_google_email_is_updated_on_sign_in(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    _google_answers(browser, fake)
    _sign_up(browser, THIS_YEAR - 30)

    _google_answers(TestClient(app, base_url=BASE_URL), fake, email="new@example.com")

    assert _users(app)[0].email == "new@example.com"


# Refusals


def test_cancelling_at_google_comes_back_as_cancelled(browser: TestClient) -> None:
    query = _start(browser)
    response = browser.get(
        f"/api/auth/google/callback?error=access_denied&state={query['state']}",
        follow_redirects=False,
    )

    assert _location(response) == "/?signin=cancelled"


def test_an_unverified_google_email_is_refused(browser: TestClient, fake: FakeGoogle) -> None:
    assert _google_answers(browser, fake, email_verified=False) == "/?signin=unverified"


def test_a_forged_token_is_refused(app: FastAPI, browser: TestClient, fake: FakeGoogle) -> None:
    query = _start(browser)
    fake.will_return("code-1", fake.other_key_token(nonce=query["nonce"]))

    response = browser.get(
        f"/api/auth/google/callback?code=code-1&state={query['state']}", follow_redirects=False
    )

    assert _location(response) == "/?signin=failed"
    assert _users(app) == []


def test_a_state_from_another_browser_is_refused(app: FastAPI, fake: FakeGoogle) -> None:
    victim, attacker = TestClient(app, base_url=BASE_URL), TestClient(app, base_url=BASE_URL)
    query = _start(attacker)
    fake.will_return("code-1", fake.id_token(nonce=query["nonce"]))

    response = victim.get(
        f"/api/auth/google/callback?code=code-1&state={query['state']}", follow_redirects=False
    )

    assert _location(response) == "/?signin=failed"
    assert fake.token_requests == []  # refused before the code is even exchanged


def test_a_state_can_be_used_only_once(browser: TestClient, fake: FakeGoogle) -> None:
    query = _start(browser)
    fake.will_return("code-1", fake.id_token(nonce=query["nonce"]))
    url = f"/api/auth/google/callback?code=code-1&state={query['state']}"

    assert _location(browser.get(url, follow_redirects=False)) == "/signup"
    assert _location(browser.get(url, follow_redirects=False)) == "/?signin=failed"


def test_an_expired_state_asks_to_start_again(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    query = _start(browser)
    with _session(app) as session:
        past = datetime.now(UTC) - timedelta(minutes=1)
        session.execute(update(OAuthState).values(expires_at=past))
        session.commit()
    fake.will_return("code-1", fake.id_token(nonce=query["nonce"]))

    response = browser.get(
        f"/api/auth/google/callback?code=code-1&state={query['state']}", follow_redirects=False
    )

    assert _location(response) == "/?signin=expired"


# Connect Google (existing invite-link players)


def test_an_invite_player_connects_google_and_then_signs_in_with_it(
    app: FastAPI, fake: FakeGoogle
) -> None:
    player = log_in(app, "Alex")

    assert (
        _google_answers(player, fake, intent="connect", sub="2002") == "/profile?google=connected"
    )

    assert player.get("/api/me").json()["google_connected"] is True
    later = TestClient(app, base_url=BASE_URL)
    assert _google_answers(later, fake, sub="2002") == "/"
    assert later.get("/api/me").json()["name"] == "Alex"


def test_a_google_account_used_by_another_player_cant_be_connected(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    _google_answers(browser, fake, sub="3003")
    _sign_up(browser, THIS_YEAR - 30)
    player = log_in(app, "Alex")

    assert _google_answers(player, fake, intent="connect", sub="3003") == "/profile?google=taken"
    assert player.get("/api/me").json()["google_connected"] is False


def test_connect_needs_a_logged_in_player(browser: TestClient) -> None:
    response = browser.get("/api/auth/google/start?intent=connect", follow_redirects=False)

    assert _location(response) == "/?signin=failed"


def test_an_existing_account_isnt_merged_by_matching_email(
    app: FastAPI, browser: TestClient, fake: FakeGoogle
) -> None:
    log_in(app, "Alex")
    with _session(app) as session:
        session.execute(update(User).where(User.name == "Alex").values(email="alex@example.com"))
        session.commit()

    assert _google_answers(browser, fake, sub="4004", email="alex@example.com") == "/signup"
