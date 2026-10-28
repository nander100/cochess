"""The optional daily token limit (SPEC_V2 §12): off by default, per player, rolling 24 hours."""

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.config import Settings
from app.db.models import LlmUsageRow
from app.main import create_app
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import log_in
from tests.coach_fakes import FakeCoachClient

ANSWER = "### Overall\nA classic: 17. Rd8# finished it."  # FAKE_USAGE: 2,500 tokens a call


def make(limit: int | None) -> tuple[FastAPI, TestClient, str]:
    settings = Settings(_env_file=None, database_url="sqlite://", user_daily_token_limit=limit)
    app = create_app(settings, FakeCoachClient(*[ANSWER] * 5))
    client = log_in(app, "Owner")
    return app, client, analyzed_game(client)


def ask(client: TestClient, game_id: str) -> int:
    return client.post(
        f"/api/games/{game_id}/chat", json={"message": "Why?", "path_uci": []}
    ).status_code


def test_no_limit_by_default() -> None:
    assert Settings(_env_file=None).user_daily_token_limit is None
    _, client, game_id = make(None)

    assert client.post(f"/api/games/{game_id}/synopsis").status_code == 200
    assert ask(client, game_id) != 429


def test_coach_calls_stop_at_the_limit() -> None:
    _, client, game_id = make(2_500)
    assert client.post(f"/api/games/{game_id}/synopsis").status_code == 200  # uses 2,500

    response = client.post(f"/api/games/{game_id}/chat", json={"message": "Why?", "path_uci": []})

    assert response.status_code == 429
    assert "coaching allowance" in response.json()["detail"]
    assert client.post(f"/api/games/{game_id}/moments/1/start").status_code == 429
    assert client.post("/api/onboarding/report").status_code == 429


def test_the_limit_is_per_player_and_per_day() -> None:
    app, client, game_id = make(2_500)
    client.post(f"/api/games/{game_id}/synopsis")
    other = log_in(app, "Sam")
    other_game = analyzed_game(other)

    assert other.post(f"/api/games/{other_game}/synopsis").status_code == 200

    with app.state.session_factory() as session:
        yesterday = datetime.now(UTC) - timedelta(days=1, minutes=1)
        session.execute(update(LlmUsageRow).values(created_at=yesterday))
        session.commit()
    assert ask(client, game_id) != 429
