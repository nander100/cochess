"""POST /api/onboarding/import: the newest games that fill the assessment's empty slots, from a
faked Chess.com (owner request 2026-11-06: at most the 12 the slots need)."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.test_onboarding_api import ME, make, pgn, submit
from tests.importers.fakes import chesscom_api, chesscom_game, recording

WIN = {"white": "1-0", "black": "0-1"}
LOSS = {"white": "0-1", "black": "1-0"}


def game(n: int, color: str, result: str, time_class: str = "rapid") -> dict[str, Any]:
    """Chess.com game `n` (a higher n is newer) with the player on `color`."""
    return chesscom_game(n, pgn=pgn(n, color, result), time_class=time_class)


def fake(app: FastAPI, games: list[dict[str, Any]]) -> list[httpx.Request]:
    """One October archive with `games`, oldest first as Chess.com sends them."""
    transport, seen = recording(chesscom_api({"2026/10": games}, user=ME))
    app.state.import_transport = transport
    app.state.settings.imports.cooldown_seconds = 0
    return seen


def setup() -> tuple[TestClient, FastAPI]:
    client, _, app = make()
    client.patch("/api/settings", json={"chesscom_username": ME})
    return client, app


def test_the_newest_three_of_each_kind_are_picked_and_nothing_else() -> None:
    client, app = setup()
    kinds = [("white", WIN), ("white", LOSS), ("black", WIN), ("black", LOSS)]
    history = [game(n, color, outcome[color]) for n, (color, outcome) in enumerate(kinds * 5)]
    history += [game(40, "white", "1/2-1/2"), game(41, "white", "1-0", time_class="blitz")]
    seen = fake(app, history)

    body = client.post("/api/onboarding/import", json={"platform": "chesscom"}).json()

    assert body["username"] == ME and body["missing"] == []
    # Newest first: games 19..8 are the latest three of each kind; the draw and blitz are skipped.
    assert [g["external_id"] for g in body["games"]] == [str(1000 + n) for n in range(19, 7, -1)]
    assert seen[0].url.path == f"/pub/player/{ME}/games/archives"


def test_filled_slots_and_games_already_added_are_left_out() -> None:
    client, app = setup()
    submit(client, [pgn(1, "white", "1-0")], ["white"])  # one white win already in
    fake(app, [game(n, "white", "1-0") for n in range(1, 6)])

    body = client.post("/api/onboarding/import", json={"platform": "chesscom"}).json()

    # Game 1 is a duplicate; two more white wins fill that slot.
    assert [g["external_id"] for g in body["games"]] == ["1005", "1004"]
    assert {m["slot"]: m["count"] for m in body["missing"]} == {
        "white_loss": 3, "black_win": 3, "black_loss": 3,
    }  # fmt: skip


def test_games_without_the_players_name_are_never_picked() -> None:
    client, app = setup()
    stranger = chesscom_game(1, pgn=pgn(1, "white", "1-0").replace(ME, "someone_else"))
    fake(app, [stranger])

    body = client.post("/api/onboarding/import", json={"platform": "chesscom"}).json()

    assert body["games"] == [] and body["fetched"] == 1


def test_the_main_time_control_is_asked_of_the_platform() -> None:
    client, app = setup()
    fake(app, [game(1, "white", "1-0", time_class="blitz")])

    body = client.post("/api/onboarding/import", json={"platform": "chesscom"}).json()

    assert body["fetched"] == 0  # the importer keeps only rapid games, the player's main one


@pytest.mark.parametrize(("status", "expected"), [(404, 404), (429, 429), (503, 502)])
def test_platform_failures_are_explained(status: int, expected: int) -> None:
    client, app = setup()
    app.state.import_transport = httpx.MockTransport(lambda request: httpx.Response(status))
    app.state.settings.imports.cooldown_seconds = 0

    assert (
        client.post("/api/onboarding/import", json={"platform": "chesscom"}).status_code == expected
    )


def test_a_platform_without_a_username_asks_for_one() -> None:
    client, _, app = make()
    fake(app, [])

    response = client.post("/api/onboarding/import", json={"platform": "lichess"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Add your Lichess username on your profile first."
