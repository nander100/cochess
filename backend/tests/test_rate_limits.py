"""Rate limits in the database (SPEC_V4 §12.2): they survive restarts and aren't shared between
staging and production. Fixed windows counted with an atomic upsert and committed at once (a
failed login still counts); the client's address comes from the right of X-Forwarded-For, behind
the configured number of trusted proxies."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import RateLimits, Settings
from app.db.models import RateLimitRow
from app.limits import client_ip, hit
from app.main import create_app
from tests import billing_fakes
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import BASE_URL, log_in
from tests.coach_fakes import FakeCoachClient
from tests.databases import fresh_database_url

NOW = datetime(2026, 11, 24, 12, 0, 30, tzinfo=UTC)


def _app(**limits: Any) -> FastAPI:
    settings = Settings(
        _env_file=None, database_url=fresh_database_url(), rate_limits=RateLimits(**limits)
    )
    return create_app(settings, FakeCoachClient(*["### Overall\nFine."] * 20))


def test_a_window_allows_the_limit_then_says_how_long_to_wait(db_session: Session) -> None:
    results = [hit(db_session, "k", 3, 60, NOW) for _ in range(4)]

    assert results[:3] == [None, None, None]
    assert results[3] == 30  # seconds to the next window
    assert hit(db_session, "other", 3, 60, NOW) is None  # each key has its own count


def test_a_new_window_starts_again_and_old_windows_are_cleared(db_session: Session) -> None:
    for _ in range(3):
        hit(db_session, "k", 3, 60, NOW)

    assert hit(db_session, "k", 3, 60, NOW + timedelta(seconds=60)) is None

    rows = db_session.scalars(select(RateLimitRow).where(RateLimitRow.key == "k")).all()
    assert [r.count for r in rows] == [1]


def test_an_attempt_counts_even_if_the_request_then_fails(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        hit(session, "k", 1, 60, NOW)
        session.rollback()
    with app.state.session_factory() as session:
        assert hit(session, "k", 1, 60, NOW) == 30


class _Request:
    def __init__(self, host: str, forwarded: str | None) -> None:
        self.client = type("Client", (), {"host": host})()
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}


@pytest.mark.parametrize(
    ("hops", "forwarded", "expected"),
    [
        (0, "1.1.1.1", "10.0.0.5"),  # no trusted proxy: the header is ignored
        (2, "203.0.113.9, 10.0.0.2", "203.0.113.9"),  # Caddy, then nginx
        (2, "6.6.6.6, 203.0.113.9, 10.0.0.2", "203.0.113.9"),  # a forged left entry
        (2, None, "10.0.0.5"),
        (2, "10.0.0.2", "10.0.0.2"),  # fewer entries than proxies: the leftmost
    ],
)
def test_the_client_address_comes_from_behind_the_trusted_proxies(
    hops: int, forwarded: str | None, expected: str
) -> None:
    assert client_ip(_Request("10.0.0.5", forwarded), hops) == expected  # type: ignore[arg-type]


def test_login_links_are_limited_per_address() -> None:
    client = TestClient(_app(logins_per_minute=2), base_url=BASE_URL)

    codes = [client.post("/api/auth/redeem", json={"token": "nope"}).status_code for _ in range(3)]

    assert codes == [400, 400, 429]
    limited = client.post("/api/auth/redeem", json={"token": "nope"})
    assert "Retry-After" in limited.headers
    assert "Too many" in limited.json()["detail"]


def test_google_sign_in_is_limited_per_address() -> None:
    client = TestClient(_app(logins_per_minute=1), base_url=BASE_URL, follow_redirects=False)

    client.get("/api/auth/google/callback?code=x&state=y")

    assert client.get("/api/auth/google/callback?code=x&state=y").status_code == 429


def test_coach_calls_are_limited_per_player_unmetered_or_not() -> None:
    app = _app(coach_per_minute=2)
    client = log_in(app, "Chatty")  # unmetered: the limit still applies
    game = analyzed_game(client, "white")
    body = {"message": "Why?", "path_uci": []}

    codes = [client.post(f"/api/games/{game}/chat", json=body).status_code for _ in range(3)]

    assert codes == [200, 200, 429]
    other = log_in(app, "Quiet")
    other_game = analyzed_game(other, "black")
    assert other.post(f"/api/games/{other_game}/chat", json=body).status_code == 200


def test_exports_are_limited_per_player_per_day() -> None:
    client = log_in(_app(exports_per_day=2), "Exporter")

    codes = [client.post("/api/me/export").status_code for _ in range(3)]

    assert codes == [200, 200, 429]
    assert "tomorrow" in client.post("/api/me/export").json()["detail"]


def test_checkouts_are_limited_per_player_per_minute() -> None:
    app = _app(checkouts_per_minute=1)
    billing_fakes.install(app)
    client = log_in(app, "Buyer")

    first = client.post("/api/billing/checkout", json={"product": "top_up"})
    second = client.post("/api/billing/checkout", json={"product": "top_up"})

    assert (first.status_code, second.status_code) == (200, 429)


def test_limits_live_in_the_database(app: FastAPI) -> None:
    client = TestClient(app, base_url=BASE_URL)
    client.post("/api/auth/redeem", json={"token": "nope"})

    with app.state.session_factory() as session:
        count = session.scalar(select(func.count()).select_from(RateLimitRow))
    assert count == 1
