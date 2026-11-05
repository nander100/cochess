"""GET / PATCH /api/settings (SPEC_V3 §4.3): per-player settings."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.auth_helpers import log_in

DEFAULTS = {
    "theme": "light",
    "board_scheme": "blue",
    "piece_set": "cburnett",
    "sounds": False,
    "engine_panel": False,
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
    ],
    ids=["theme", "scheme", "pieces", "sounds"],
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
