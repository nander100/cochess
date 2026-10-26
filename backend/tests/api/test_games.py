from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import chess
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Game, User
from tests.auth_helpers import log_in
from tests.pgn_fixtures import USER_FIXTURES, owner_color, read_pgn

SHORT_GAME = {"pgn": "1. e4 e5 *", "user_color": "white"}


def game_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"pgn": read_pgn("annotated_clock_game.pgn"), "user_color": "black"}
    return {**body, **overrides}


def test_create_game_returns_positions(client: TestClient) -> None:
    response = client.post("/api/games", json=game_body())

    assert response.status_code == 201
    data = response.json()
    assert len(data["positions"]) == 14
    assert data["positions"][2] == {
        "ply": 3,
        "fen_before": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        "san": "Nf3",
        "uci": "g1f3",
        "clock_s": 598.0,
    }
    assert data["final_is_terminal"] is True
    assert chess.Board(data["final_fen"]).is_checkmate()


def test_a_game_belongs_to_its_uploader_and_keeps_their_profile_at_upload(
    app: FastAPI, db_session: Session
) -> None:
    client = log_in(app, "Sam", elo=1610, playstyle="aggressive, likes 1...e5")

    response = client.post("/api/games", json=game_body())

    game = db_session.get(Game, response.json()["game_id"])
    sam = db_session.scalars(select(User).where(User.name == "Sam")).one()
    assert game is not None
    assert (game.user_id, game.user_color, game.elo, game.playstyle) == (
        sam.id,
        "black",
        1610,
        "aggressive, likes 1...e5",
    )
    assert (game.user_result, game.source, game.status) == ("win", "single", "uploaded")
    assert game.played_at == datetime(2026, 1, 1, tzinfo=UTC)  # from the Date header
    assert game.headers["TimeControl"] == "600+5"
    assert "Book move" not in game.pgn


def test_a_game_without_a_date_is_dated_at_upload(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/games", json=SHORT_GAME)

    game = db_session.get(Game, response.json()["game_id"])
    assert game is not None
    assert game.played_at == game.created_at
    assert game.user_result is None  # "*": unfinished


@pytest.mark.parametrize(
    "profile", [{"elo": None}, {"time_control": None}], ids=["no-elo", "no-time-control"]
)
def test_an_incomplete_profile_must_be_filled_in_first(
    app: FastAPI, profile: dict[str, Any]
) -> None:
    client = log_in(app, "New", **profile)

    response = client.post("/api/games", json=SHORT_GAME)

    assert response.status_code == 409
    assert "Fill in your profile" in response.json()["detail"]


def test_uploading_needs_a_login(anon_client: TestClient) -> None:
    assert anon_client.post("/api/games", json=SHORT_GAME).status_code == 401


def test_invalid_pgn_returns_clear_error(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/games", json=game_body(pgn="1. e4 e5 2. Ke3 *"))

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "illegal_move",
            "message": "Move 2 (White): Ke3 is not a legal move in that position.",
            "move_number": 2,
        }
    }
    assert db_session.query(Game).count() == 0


def test_pgn_size_limit_comes_from_settings(client: TestClient, app: FastAPI) -> None:
    app.state.settings.limits.max_pgn_chars = 50

    response = client.post("/api/games", json=game_body())

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "too_large"


@pytest.mark.parametrize(
    "overrides",
    [{"user_color": "red"}, {"user_color": None}, {"pgn": ""}, {"pgn": None}],
    ids=["color", "color-null", "pgn-empty", "pgn-null"],
)
def test_invalid_fields_are_rejected(client: TestClient, overrides: dict[str, Any]) -> None:
    response = client.post("/api/games", json=game_body(**overrides))

    assert response.status_code == 422


@pytest.mark.parametrize("path", USER_FIXTURES, ids=lambda p: p.name)
def test_owner_games_are_accepted(client: TestClient, path: Path) -> None:
    body = game_body(pgn=path.read_text(), user_color=owner_color(path))

    response = client.post("/api/games", json=body)

    assert response.status_code == 201, response.json()


class TestDailyGameCap:
    def test_new_games_stop_at_the_daily_cap(self, app: FastAPI, client: TestClient) -> None:
        app.state.settings.limits.max_games_per_day = 2

        statuses = [client.post("/api/games", json=SHORT_GAME).status_code for _ in range(3)]

        assert statuses == [201, 201, 429]
        detail = client.post("/api/games", json=SHORT_GAME).json()["detail"]
        assert "at most 2 new games a day per player" in detail

    def test_the_cap_is_per_player(self, app: FastAPI, client: TestClient) -> None:
        app.state.settings.limits.max_games_per_day = 1
        client.post("/api/games", json=SHORT_GAME)

        other = log_in(app, "Sam")

        assert client.post("/api/games", json=SHORT_GAME).status_code == 429
        assert other.post("/api/games", json=SHORT_GAME).status_code == 201

    def test_games_older_than_a_day_and_onboarding_games_do_not_count(
        self, app: FastAPI, client: TestClient, db_session: Session
    ) -> None:
        app.state.settings.limits.max_games_per_day = 1
        owner = db_session.scalars(select(User).where(User.name == "Owner")).one()
        now = datetime.now(UTC)
        for created_at, source in (
            (now - timedelta(days=1, minutes=1), "single"),
            (now, "onboarding"),
        ):
            db_session.add(
                Game(user_id=owner.id, pgn="1. e4 *", user_color="white", elo=1200, headers={},
                     source=source, created_at=created_at)
            )  # fmt: skip
        db_session.commit()

        assert client.post("/api/games", json=SHORT_GAME).status_code == 201
