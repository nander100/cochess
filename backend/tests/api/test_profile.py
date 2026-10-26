from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.auth_helpers import log_in


def test_read_profile(app: FastAPI) -> None:
    client = log_in(app, "Alex", elo=1420, time_control="blitz", playstyle="solid")

    assert client.get("/api/me").json() == {
        "name": "Alex",
        "elo": 1420,
        "time_control": "blitz",
        "playstyle": "solid",
        "complete": True,
    }


def test_a_new_player_has_an_incomplete_profile(app: FastAPI) -> None:
    client = log_in(app, "New", elo=None, time_control=None)

    assert client.get("/api/me").json()["complete"] is False


def test_update_changes_only_the_fields_sent(app: FastAPI) -> None:
    client = log_in(app, "New", elo=None, time_control=None, playstyle="solid")

    response = client.patch("/api/me", json={"elo": 1500, "time_control": "rapid"})

    assert response.status_code == 200
    assert response.json() == {
        "name": "New",
        "elo": 1500,
        "time_control": "rapid",
        "playstyle": "solid",
        "complete": True,
    }
    assert client.get("/api/me").json() == response.json()


def test_a_blank_playstyle_clears_it(client: TestClient) -> None:
    client.patch("/api/me", json={"playstyle": "aggressive"})

    response = client.patch("/api/me", json={"playstyle": "   "})

    assert response.json()["playstyle"] is None


def test_renaming_keeps_names_unique_ignoring_case(app: FastAPI, client: TestClient) -> None:
    log_in(app, "Sam")

    assert client.patch("/api/me", json={"name": "sam"}).status_code == 409
    assert client.patch("/api/me", json={"name": " Owner2 "}).json()["name"] == "Owner2"
    assert client.patch("/api/me", json={"name": "OWNER2"}).json()["name"] == "OWNER2"


@pytest.mark.parametrize(
    "body",
    [
        {"elo": 99},
        {"elo": 3001},
        {"elo": "strong"},
        {"time_control": "correspondence"},
        {"playstyle": "x" * 501},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 61},
    ],
    ids=["elo-low", "elo-high", "elo-text", "tc", "playstyle-long", "name-empty", "name-blank",
         "name-long"],
)  # fmt: skip
def test_invalid_profile_fields_are_rejected(client: TestClient, body: dict[str, Any]) -> None:
    assert client.patch("/api/me", json=body).status_code == 422


def test_the_profile_needs_a_login(anon_client: TestClient) -> None:
    assert anon_client.get("/api/me").status_code == 401
    assert anon_client.patch("/api/me", json={"elo": 1500}).status_code == 401
