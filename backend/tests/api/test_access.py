from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Limits, Settings
from app.db.models import Game
from app.main import create_app

CODE = "knight-to-f3"
GAME = {"pgn": "1. e4 e5 *", "user_color": "white", "elo": 1200}


def app_with(**settings: Any) -> Any:
    return create_app(Settings(_env_file=None, database_url="sqlite://", **settings))


class TestAccessGate:
    @pytest.mark.parametrize("headers", [{}, {"X-Access-Code": "wrong"}, {"X-Access-Code": ""}])
    def test_api_requests_need_the_right_code(self, headers: dict[str, str]) -> None:
        response = TestClient(app_with(access_code=CODE)).get("/api/engine-config", headers=headers)

        assert response.status_code == 401
        assert response.json() == {"detail": "Enter the access code to use CoChess."}
        # The page stays cross-origin isolated even on the gate's error responses.
        assert response.headers["Cross-Origin-Embedder-Policy"] == "require-corp"

    def test_the_right_code_opens_every_endpoint(self) -> None:
        client = TestClient(app_with(access_code=CODE))
        headers = {"X-Access-Code": CODE}

        assert client.get("/api/engine-config", headers=headers).status_code == 200
        assert client.post("/api/games", json=GAME, headers=headers).status_code == 201

    def test_coach_endpoints_are_gated_too(self) -> None:
        client = TestClient(app_with(access_code=CODE))

        assert client.post("/api/games/x/chat", json={"message": "hi"}).status_code == 401

    def test_health_is_not_gated(self) -> None:
        assert TestClient(app_with(access_code=CODE)).get("/api/health").status_code == 200

    def test_without_an_access_code_configured_the_gate_is_off(self, client: TestClient) -> None:
        assert client.get("/api/engine-config").status_code == 200


class TestDailyGameCap:
    def test_new_games_stop_at_the_daily_cap(self) -> None:
        client = TestClient(app_with(limits=Limits(max_games_per_day=2)))

        statuses = [client.post("/api/games", json=GAME).status_code for _ in range(3)]

        assert statuses == [201, 201, 429]
        detail = client.post("/api/games", json=GAME).json()["detail"]
        assert "at most 2 new games a day" in detail

    def test_games_older_than_a_day_do_not_count(self) -> None:
        app = app_with(limits=Limits(max_games_per_day=1))
        old = datetime.now(UTC) - timedelta(days=1, minutes=1)
        with app.state.session_factory() as session:
            session.add(
                Game(pgn="1. e4 *", user_color="white", elo=1200, playstyle=None, headers={},
                     created_at=old)
            )  # fmt: skip
            session.commit()

        assert TestClient(app).post("/api/games", json=GAME).status_code == 201
