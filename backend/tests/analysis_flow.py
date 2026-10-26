"""Run a game through the API's scan and verify steps with fake engine results."""

from typing import Any

from fastapi.testclient import TestClient

from tests.engine_fakes import fake_result
from tests.pgn_fixtures import read_pgn


def analyzed_game(client: TestClient, pgn_name: str = "opera_game.pgn", elo: int = 1350) -> str:
    """Create, scan and verify a game; returns its id. The summary is stored afterwards."""
    response = client.post(
        "/api/games", json={"pgn": read_pgn(pgn_name), "user_color": "white", "elo": elo}
    )
    assert response.status_code == 201, response.text
    game: dict[str, Any] = response.json()
    fens = [p["fen_before"] for p in game["positions"]]
    if not game["final_is_terminal"]:
        fens.append(game["final_fen"])

    scan = client.post(
        f"/api/games/{game['game_id']}/engine/scan",
        json={"results": [fake_result(fen, "scan", plies=1) for fen in fens]},
    )
    verify_fens = scan.json()["verify_fens"]
    verify = client.post(
        f"/api/games/{game['game_id']}/engine/verify",
        json={"results": [fake_result(f, "verify", lines=4, plies=10) for f in verify_fens]},
    )
    assert verify.json()["summary_ready"] is True
    game_id: str = game["game_id"]
    return game_id
