"""POST /api/import (SPEC_V3 §10): recent games as a review table, against faked platforms."""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Game
from tests.auth_helpers import log_in
from tests.importers.fakes import (
    chesscom_api,
    chesscom_game,
    lichess_game,
    lichess_games,
    recording,
)


@pytest.fixture(autouse=True)
def no_cooldown(app: FastAPI) -> None:
    app.state.settings.imports.cooldown_seconds = 0


def fake(app: FastAPI, handler: httpx.MockTransport | None = None) -> None:
    app.state.import_transport = handler or httpx.MockTransport(
        lichess_games(lichess_game(1), lichess_game(2))
    )


def test_a_platform_without_a_username_asks_for_one(app: FastAPI, client: TestClient) -> None:
    fake(app)

    response = client.post("/api/import", json={"platform": "lichess"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Add your Lichess username on your profile first."


def test_games_come_back_with_the_color_detected(app: FastAPI, client: TestClient) -> None:
    client.patch("/api/settings", json={"lichess_username": "me"})
    fake(app)

    body = client.post("/api/import", json={"platform": "lichess"}).json()

    assert body["username"] == "me"
    assert [(r["external_id"], r["user_color"], r["category"]) for r in body["games"]] == [
        ("lc000001", "white", "rapid"),
        ("lc000002", "white", "rapid"),
    ]
    assert not any(r["already_imported"] for r in body["games"])
    assert body["games"][0]["pgn"].startswith('[Event "Rated game"]')


def test_an_added_game_is_marked_and_cannot_be_added_twice(
    app: FastAPI, client: TestClient
) -> None:
    client.patch("/api/settings", json={"lichess_username": "me"})
    fake(app)
    first_body = client.post("/api/import", json={"platform": "lichess"}).json()
    first, first_left = first_body["games"][0], first_body["games_left_today"]
    added = client.post(
        "/api/games",
        json={"pgn": first["pgn"], "external": {"platform": "lichess", "external_id": "lc000001"}},
    )
    assert added.status_code == 201, added.text

    again_body = client.post("/api/import", json={"platform": "lichess"}).json()
    again = again_body["games"]

    assert [r["already_imported"] for r in again] == [True, False]
    assert again_body["games_left_today"] == first_left - 1  # imports count toward the cap
    duplicate = client.post(
        "/api/games",
        json={"pgn": first["pgn"], "external": {"platform": "lichess", "external_id": "lc000001"}},
    )
    assert duplicate.status_code == 409
    with app.state.session_factory() as session:
        game = session.scalars(select(Game)).one()
    assert (game.external_source, game.external_id, game.user_color) == (
        "lichess",
        "lc000001",
        "white",
    )


def test_another_players_imports_do_not_count(app: FastAPI, client: TestClient) -> None:
    other = log_in(app, "Other")
    other.patch("/api/settings", json={"lichess_username": "me"})
    fake(app)
    pgn = other.post("/api/import", json={"platform": "lichess"}).json()["games"][0]["pgn"]
    other.post(
        "/api/games",
        json={"pgn": pgn, "external": {"platform": "lichess", "external_id": "lc000001"}},
    )
    client.patch("/api/settings", json={"lichess_username": "me"})

    rows = client.post("/api/import", json={"platform": "lichess"}).json()["games"]

    assert not any(r["already_imported"] for r in rows)


def test_chesscom_filters_and_the_cap_reach_the_platform(app: FastAPI, client: TestClient) -> None:
    client.patch("/api/settings", json={"chesscom_username": "me"})
    transport, seen = recording(chesscom_api({"2026/10": [chesscom_game(n) for n in range(60)]}))
    fake(app, transport)

    body = client.post(
        "/api/import", json={"platform": "chesscom", "max": 99, "tc": "rapid"}
    ).json()

    assert len(body["games"]) == 50  # IMPORTS__MAX_GAMES
    assert body["games"][0]["external_id"] == "1059"  # newest first
    assert seen[0].url.path == "/pub/player/me/games/archives"


@pytest.mark.parametrize(
    ("status", "expected", "words"),
    [(404, 404, "has no player called me"), (429, 429, "slow down"), (500, 502, "isn't answering")],
)
def test_platform_failures_are_explained(
    app: FastAPI, client: TestClient, status: int, expected: int, words: str
) -> None:
    client.patch("/api/settings", json={"chesscom_username": "me"})
    fake(app, httpx.MockTransport(lambda request: httpx.Response(status)))

    response = client.post("/api/import", json={"platform": "chesscom"})

    assert response.status_code == expected
    assert words in response.json()["detail"]


def test_imports_are_spaced_out_per_player(app: FastAPI, client: TestClient) -> None:
    app.state.settings.imports.cooldown_seconds = 60
    client.patch("/api/settings", json={"lichess_username": "me"})
    fake(app)
    assert client.post("/api/import", json={"platform": "lichess"}).status_code == 200

    response = client.post("/api/import", json={"platform": "lichess"})

    assert response.status_code == 429
    assert "before importing again" in response.json()["detail"]


def test_bad_requests_are_rejected(client: TestClient) -> None:
    assert client.post("/api/import", json={"platform": "chess24"}).status_code == 422
    assert client.post("/api/import", json={"platform": "lichess", "max": 0}).status_code == 422
    bad_id = {
        "pgn": "1. e4 e5 *",
        "user_color": "white",
        "external": {"platform": "lichess", "external_id": "../x"},
    }
    assert client.post("/api/games", json=bad_id).status_code == 422


def test_importing_needs_a_login(anon_client: TestClient) -> None:
    assert anon_client.post("/api/import", json={"platform": "lichess"}).status_code == 401
