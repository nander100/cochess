"""Run a game through the API's scan and verify steps with fake engine results."""

from typing import Any

from fastapi.testclient import TestClient

from app.analysis.pgn import parse_pgn
from tests.engine_fakes import fake_result
from tests.pgn_fixtures import read_pgn


def analyzed_game(client: TestClient, pgn_name: str = "opera_game.pgn", elo: int = 1350) -> str:
    """Create, scan and verify a game as the logged-in player, after setting their profile Elo
    (games take it from the profile). Returns the game id; the summary is stored afterwards."""
    assert client.patch("/api/me", json={"elo": elo}).status_code == 200
    response = client.post("/api/games", json={"pgn": read_pgn(pgn_name), "user_color": "white"})
    assert response.status_code == 201, response.text
    game: dict[str, Any] = response.json()
    fens = [p["fen_before"] for p in game["positions"]]
    if not game["final_is_terminal"]:
        fens.append(game["final_fen"])
    analyze(client, game["game_id"], fens)
    game_id: str = game["game_id"]
    return game_id


def analyze_pgn(client: TestClient, game_id: str, pgn: str) -> None:
    """Scan and verify an already-uploaded game (e.g. an onboarding game) from its PGN."""
    parsed = parse_pgn(pgn, max_chars=100_000, max_plies=600)
    fens = [p.fen_before for p in parsed.positions]
    if not parsed.final_is_terminal:
        fens.append(parsed.final_fen)
    analyze(client, game_id, fens)


def analyze(client: TestClient, game_id: str, fens: list[str]) -> None:
    scan = client.post(
        f"/api/games/{game_id}/engine/scan",
        json={"results": [fake_result(fen, "scan", plies=1) for fen in fens]},
    )
    verify_fens = scan.json()["verify_fens"]
    verify = client.post(
        f"/api/games/{game_id}/engine/verify",
        json={"results": [fake_result(f, "verify", lines=4, plies=10) for f in verify_fens]},
    )
    assert verify.json()["summary_ready"] is True
