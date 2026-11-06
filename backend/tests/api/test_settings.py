"""GET / PATCH /api/settings (SPEC_V3 §4.3): per-player settings."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.auth_helpers import log_in
from tests.coach.test_chat import chat, payload_of
from tests.coach.test_chat import setup as chat_setup

DEFAULTS = {
    "theme": "light",
    "board_scheme": "blue",
    "piece_set": "cburnett",
    "sounds": False,
    "engine_panel": False,
    "coach_detail_level": "auto",
    "playback_seconds": 1.5,
    "chesscom_username": "",
    "lichess_username": "",
    "effective_detail_level": "standard",  # "auto" for the test player's 1350 (intermediate)
}


def test_a_new_player_has_the_defaults(client: TestClient) -> None:
    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == DEFAULTS


def test_only_the_fields_sent_change_and_they_are_kept(client: TestClient) -> None:
    first = client.patch("/api/settings", json={"theme": "dark", "piece_set": "merida"})
    second = client.patch("/api/settings", json={"sounds": True})

    assert first.json() == {**DEFAULTS, "theme": "dark", "piece_set": "merida"}
    assert second.json() == {**DEFAULTS, "theme": "dark", "piece_set": "merida", "sounds": True}
    assert client.get("/api/settings").json() == second.json()


@pytest.mark.parametrize(
    "body",
    [
        {"theme": "sepia"},
        {"board_scheme": "brown"},
        {"piece_set": "california"},
        {"sounds": "loud"},
        {"coach_detail_level": "expert"},
        {"playback_seconds": 0.5},
        {"playback_seconds": 3.5},
        {"chesscom_username": "has space"},
        {"lichess_username": "x" * 51},
    ],
    ids=[
        "theme",
        "scheme",
        "pieces",
        "sounds",
        "detail",
        "too fast",
        "too slow",
        "space",
        "too long",
    ],
)
def test_unknown_values_are_rejected(client: TestClient, body: dict[str, Any]) -> None:
    response = client.patch("/api/settings", json=body)

    assert response.status_code == 422
    assert client.get("/api/settings").json() == DEFAULTS


def test_each_player_has_their_own_settings(app: FastAPI, client: TestClient) -> None:
    other = log_in(app, "Other")
    client.patch("/api/settings", json={"theme": "dark"})

    assert other.get("/api/settings").json() == DEFAULTS


def test_settings_need_a_login(anon_client: TestClient) -> None:
    assert anon_client.get("/api/settings").status_code == 401
    assert anon_client.patch("/api/settings", json={"theme": "dark"}).status_code == 401


@pytest.mark.parametrize(
    ("elo", "level"), [(850, "plain"), (1350, "standard"), (1950, "technical"), (None, "standard")]
)
def test_auto_detail_follows_the_rating_band(app: FastAPI, elo: int | None, level: str) -> None:
    player = log_in(app, f"Rated {elo}", elo=elo)

    assert player.get("/api/settings").json()["effective_detail_level"] == level


def test_a_chosen_detail_level_and_speed_are_kept_and_auto_can_come_back(
    client: TestClient,
) -> None:
    chosen = client.patch(
        "/api/settings", json={"coach_detail_level": "technical", "playback_seconds": 0.75}
    ).json()
    assert (chosen["coach_detail_level"], chosen["effective_detail_level"]) == (
        "technical", "technical"
    )  # fmt: skip
    assert chosen["playback_seconds"] == 0.75

    back = client.patch("/api/settings", json={"coach_detail_level": "auto"}).json()
    assert (back["coach_detail_level"], back["effective_detail_level"]) == ("auto", "standard")


def test_the_chosen_detail_level_reaches_the_coach() -> None:
    client, fake, _, game_id = chat_setup("An answer.")
    client.patch("/api/settings", json={"coach_detail_level": "plain"})

    chat(client, game_id, "What now?")

    assert payload_of(fake, 0)["player"]["detail_level"] == "plain"


def test_usernames_are_kept_trimmed_and_can_be_cleared(client: TestClient) -> None:
    body = client.patch(
        "/api/settings", json={"chesscom_username": "nander100", "lichess_username": "alex_l"}
    ).json()
    assert (body["chesscom_username"], body["lichess_username"]) == ("nander100", "alex_l")

    cleared = client.patch("/api/settings", json={"chesscom_username": ""}).json()

    assert (cleared["chesscom_username"], cleared["lichess_username"]) == ("", "alex_l")
