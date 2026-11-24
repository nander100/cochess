"""Credits through the API (SPEC_V4 §5, §7, §14.3): every coach route is refused at zero, a call
is charged what it cost, stored coach output stays free, and the Deep tier picks its models."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth.accounts import admit
from app.billing.ledger import adjust_by_owner, balance
from app.billing.pricing import cost_microusd
from app.config import CreditSettings, PricingSettings, Settings
from app.db.models import LlmUsageRow, User
from app.main import create_app
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import BASE_URL, log_in
from tests.coach_fakes import FAKE_USAGE, FakeCoachClient
from tests.databases import fresh_database_url

ANSWER = "### Overall\nA tidy game."
CALL = cost_microusd(PricingSettings(), "fake-model", FAKE_USAGE)  # the fake's model: top rates
CREDIT = 10_000
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def _app(fake: FakeCoachClient, **settings: object) -> FastAPI:
    return create_app(Settings(_env_file=None, database_url=fresh_database_url(), **settings), fake)


def _player(app: FastAPI, name: str, microusd: int) -> tuple[TestClient, str]:
    """A metered player with this many microdollars, and an analyzed game."""
    client = log_in(app, name, metered=True)
    with app.state.session_factory() as session:
        user = session.scalars(select(User).where(User.name == name)).one()
        if microusd:
            adjust_by_owner(session, user, microusd, note="test", now=NOW)
        session.commit()
    return client, analyzed_game(client, "white")


def _balance(app: FastAPI, name: str) -> int:
    with app.state.session_factory() as session:
        user = session.scalars(select(User).where(User.name == name)).one()
        return balance(session, user.id).total


def _chat(client: TestClient, game: str) -> int:
    return client.post(
        f"/api/games/{game}/chat", json={"message": "Why?", "path_uci": []}
    ).status_code


COACH_CALLS = [
    ("/api/games/{game}/synopsis", None),
    ("/api/games/{game}/chat", {"message": "Why?", "path_uci": []}),
    ("/api/games/{game}/explain", {"path_uci": []}),
    ("/api/games/{game}/moments/1/start", None),
    ("/api/games/{game}/walkthrough", {"start_path_uci": [], "line_uci": ["e2e4"]}),
]


@pytest.mark.parametrize(("path", "body"), COACH_CALLS)
def test_every_coach_route_is_refused_at_zero(path: str, body: dict[str, object] | None) -> None:
    fake = FakeCoachClient(ANSWER)
    app = _app(fake)
    client, game = _player(app, "Zero", 0)

    response = client.post(path.format(game=game), json=body)

    assert response.status_code == 402, response.text
    assert "out of coaching credits" in response.json()["detail"]
    assert fake.requests == []  # the coach was never called


def test_a_call_is_charged_exactly_what_it_cost() -> None:
    app = _app(FakeCoachClient(ANSWER))
    client, game = _player(app, "Sam", 100 * CREDIT)

    assert client.post(f"/api/games/{game}/synopsis").status_code == 200

    assert _balance(app, "Sam") == 100 * CREDIT - CALL
    with app.state.session_factory() as session:
        row = session.scalars(select(LlmUsageRow)).one()
        assert (row.cost_microusd, row.tier) == (CALL, "standard")


def test_a_stored_synopsis_is_free_to_read_again_even_at_zero() -> None:
    app = _app(FakeCoachClient(ANSWER))
    client, game = _player(app, "Sam", CALL)  # exactly one call's worth
    assert client.post(f"/api/games/{game}/synopsis").status_code == 200
    assert _balance(app, "Sam") == 0

    again = client.post(f"/api/games/{game}/synopsis")

    assert again.status_code == 200 and "A tidy game." in again.text
    assert _chat(client, game) == 402


def test_an_unmetered_player_is_never_charged_but_the_call_is_priced() -> None:
    app = _app(FakeCoachClient(ANSWER))
    client = log_in(app, "Owner")  # the test helper's players are unmetered
    game = analyzed_game(client, "white")

    assert client.post(f"/api/games/{game}/synopsis").status_code == 200

    assert _balance(app, "Owner") == 0
    with app.state.session_factory() as session:
        assert session.scalars(select(LlmUsageRow.cost_microusd)).one() == CALL


def test_the_daily_cap_stops_coaching_whatever_the_balance() -> None:
    app = _app(FakeCoachClient(ANSWER, ANSWER), credits=CreditSettings(daily_cap_microusd=CALL))
    client, game = _player(app, "Sam", 100 * CREDIT)
    assert client.post(f"/api/games/{game}/synopsis").status_code == 200

    response = client.post(f"/api/games/{game}/chat", json={"message": "?", "path_uci": []})

    assert response.status_code == 429
    assert "today's coaching limit" in response.json()["detail"]


def test_billing_shows_the_trial_and_warns_when_it_runs_low() -> None:
    app = _app(FakeCoachClient(ANSWER))
    client, _ = _player(app, "Sam", 0)
    with app.state.session_factory() as session:
        session.execute(update(User).where(User.name == "Sam").values(status="waitlisted"))
        session.commit()
        user = session.scalars(select(User).where(User.name == "Sam")).one()
        admit(session, user, NOW)
        session.commit()

    full = client.get("/api/billing").json()
    assert (full["credits"], full["low"], full["out"]) == (50, False, False)
    assert full["history"][0]["kind"] == "trial"
    assert full["credits_per_game"] == {"standard": 3.3, "deep": 12}

    with app.state.session_factory() as session:
        user = session.scalars(select(User).where(User.name == "Sam")).one()
        adjust_by_owner(session, user, -45 * CREDIT, note="test", now=NOW)
        session.commit()
    low = client.get("/api/billing").json()
    assert (low["credits"], low["low"], low["out"]) == (5, True, False)


def test_billing_needs_a_signed_in_player(app: FastAPI) -> None:
    assert TestClient(app, base_url=BASE_URL).get("/api/billing").status_code == 401


def test_the_deep_coach_writes_with_opus_and_talks_with_sonnet() -> None:
    fake = FakeCoachClient(ANSWER, "Because.")
    app = _app(fake)
    client, game = _player(app, "Deep", 100 * CREDIT)
    assert (
        client.patch("/api/settings", json={"coach_strength": "deep"}).json()["coach_strength"]
        == "deep"
    )

    client.post(f"/api/games/{game}/synopsis")
    _chat(client, game)

    assert [r.model for r in fake.requests[:2]] == ["claude-opus-5-5", "claude-sonnet-5-5"]
    with app.state.session_factory() as session:
        assert set(session.scalars(select(LlmUsageRow.tier))) == {"deep"}


def test_standard_is_the_default_and_uses_sonnet_then_haiku() -> None:
    fake = FakeCoachClient(ANSWER, "Because.")
    app = _app(fake)
    client, game = _player(app, "Std", 100 * CREDIT)

    client.post(f"/api/games/{game}/synopsis")
    _chat(client, game)

    assert [r.model for r in fake.requests[:2]] == ["claude-sonnet-5-5", "claude-haiku-5-5"]
