"""Saved variations and PGN export over the API (SPEC_V3 §5)."""

import io

import chess.pgn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import GameVariationRow
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import log_in

LINE = {"start_path": ["e2e4", "e7e5"], "moves": ["f1c4", "g8f6"]}
NESTED = {"start_path": ["e2e4", "e7e5", "f1c4"], "moves": ["f8c5"]}


def test_nothing_is_saved_until_the_first_save(client: TestClient) -> None:
    game_id = analyzed_game(client, "white")

    assert client.get(f"/api/games/{game_id}/variations").json() == {
        "variations": [],
        "saved": False,
    }
    assert client.get(f"/api/games/{game_id}").json()["variations"] is None


def test_saved_variations_come_back_in_order(client: TestClient) -> None:
    game_id = analyzed_game(client, "white")

    saved = client.put(f"/api/games/{game_id}/variations", json={"variations": [NESTED, LINE]})

    assert saved.status_code == 200, saved.text
    expected = {"variations": [NESTED, LINE], "saved": True}
    assert client.get(f"/api/games/{game_id}/variations").json() == expected
    assert client.get(f"/api/games/{game_id}").json()["variations"] == [NESTED, LINE]


def test_an_empty_save_is_remembered(client: TestClient) -> None:
    """After the player deletes every line, the board mustn't seed moment lines again."""
    game_id = analyzed_game(client, "white")
    client.put(f"/api/games/{game_id}/variations", json={"variations": [LINE]})

    client.put(f"/api/games/{game_id}/variations", json={"variations": []})

    assert client.get(f"/api/games/{game_id}").json()["variations"] == []


def test_an_illegal_variation_rejects_the_save(client: TestClient) -> None:
    game_id = analyzed_game(client, "white")
    client.put(f"/api/games/{game_id}/variations", json={"variations": [LINE]})
    bad = {"start_path": ["e2e4"], "moves": ["e7e5", "e1e3"]}

    response = client.put(f"/api/games/{game_id}/variations", json={"variations": [LINE, bad]})

    assert response.status_code == 422
    assert "Variation 2" in response.json()["detail"]
    assert client.get(f"/api/games/{game_id}/variations").json()["variations"] == [LINE]


def test_a_variation_needs_a_move(client: TestClient) -> None:
    game_id = analyzed_game(client, "white")

    response = client.put(
        f"/api/games/{game_id}/variations",
        json={"variations": [{"start_path": ["e2e4"], "moves": []}]},
    )

    assert response.status_code == 422


def test_another_players_game_is_not_found(app: FastAPI, client: TestClient) -> None:
    game_id = analyzed_game(client, "white")
    other = log_in(app, "Other")

    assert other.get(f"/api/games/{game_id}/variations").status_code == 404
    put = other.put(f"/api/games/{game_id}/variations", json={"variations": [LINE]})
    assert put.status_code == 404
    assert other.get(f"/api/games/{game_id}/export.pgn").status_code == 404
    assert client.get(f"/api/games/{game_id}/variations").json()["saved"] is False


def test_deleting_the_game_deletes_its_variations(client: TestClient, db_session: Session) -> None:
    game_id = analyzed_game(client, "white")
    client.put(f"/api/games/{game_id}/variations", json={"variations": [LINE, NESTED]})

    assert client.delete(f"/api/games/{game_id}").status_code == 204

    count = db_session.scalar(select(func.count()).where(GameVariationRow.game_id == game_id))
    assert count == 0


def test_changing_color_keeps_the_variations(client: TestClient) -> None:
    game_id = analyzed_game(client, "white")
    client.put(f"/api/games/{game_id}/variations", json={"variations": [LINE]})

    changed = client.patch(f"/api/games/{game_id}", json={"user_color": "black"})

    assert changed.json()["variations"] == [LINE]


def test_export_downloads_the_game_with_its_variations(client: TestClient) -> None:
    game_id = analyzed_game(client, "white")
    client.put(f"/api/games/{game_id}/variations", json={"variations": [LINE, NESTED]})

    response = client.get(f"/api/games/{game_id}/export.pgn")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-chess-pgn")
    assert response.headers["content-disposition"] == (
        'attachment; filename="Paul_Morphy-vs-Duke_Karl_Count_Isouard.pgn"'
    )
    game = chess.pgn.read_game(io.StringIO(response.text))
    assert game is not None and not game.errors
    assert game.headers["Event"] == "Paris Opera"
    after_e5 = game.next().next()  # type: ignore[union-attr]
    assert [v.move.uci() for v in after_e5.variations] == ["g1f3", "f1c4"]
    assert after_e5.next().eval() is not None  # type: ignore[union-attr]


def test_an_exported_game_can_be_uploaded_again(app: FastAPI, client: TestClient) -> None:
    game_id = analyzed_game(client, "white")
    client.put(f"/api/games/{game_id}/variations", json={"variations": [LINE]})
    exported = client.get(f"/api/games/{game_id}/export.pgn").text
    original = client.get(f"/api/games/{game_id}").json()["moves"]
    other = log_in(app, "Other")

    uploaded = other.post("/api/games", json={"pgn": exported, "user_color": "white"})

    assert uploaded.status_code == 201, uploaded.text
    assert [p["uci"] for p in uploaded.json()["positions"]] == [m["uci"] for m in original]
