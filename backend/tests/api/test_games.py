from pathlib import Path
from typing import Any

import chess
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Game
from tests.pgn_fixtures import USER_FIXTURES, owner_color, read_pgn


def game_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "pgn": read_pgn("annotated_clock_game.pgn"),
        "user_color": "black",
        "elo": 1350,
        "playstyle": "aggressive, likes 1...e5",
    }
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


def test_create_game_persists_profile_and_headers(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/games", json=game_body())

    game = db_session.get(Game, response.json()["game_id"])
    assert game is not None
    assert (game.user_color, game.elo, game.playstyle) == (
        "black",
        1350,
        "aggressive, likes 1...e5",
    )
    assert game.headers["TimeControl"] == "600+5"
    assert "Book move" not in game.pgn
    assert game.created_at is not None


def test_blank_playstyle_is_stored_as_none(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/games", json=game_body(playstyle="   "))

    game = db_session.get(Game, response.json()["game_id"])
    assert game is not None
    assert game.playstyle is None


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
    [
        {"elo": 99},
        {"elo": 3001},
        {"elo": "strong"},
        {"user_color": "red"},
        {"playstyle": "x" * 501},
        {"pgn": ""},
        {"pgn": None},
    ],
    ids=["elo-low", "elo-high", "elo-text", "color", "playstyle-long", "pgn-empty", "pgn-null"],
)
def test_invalid_profile_fields_are_rejected(client: TestClient, overrides: dict[str, Any]) -> None:
    response = client.post("/api/games", json=game_body(**overrides))

    assert response.status_code == 422


def test_missing_required_fields_are_rejected(client: TestClient) -> None:
    response = client.post("/api/games", json={"pgn": "1. e4 *"})

    assert response.status_code == 422


@pytest.mark.parametrize("path", USER_FIXTURES, ids=lambda p: p.name)
def test_owner_games_are_accepted(client: TestClient, path: Path) -> None:
    body = game_body(pgn=path.read_text(), user_color=owner_color(path), playstyle=None)

    response = client.post("/api/games", json=body)

    assert response.status_code == 201, response.json()
