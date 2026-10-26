from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.engine_results import load_summary
from app.db.models import EngineResultRow, Game
from tests.engine_fakes import fake_result
from tests.pgn_fixtures import read_pgn

OPERA_PLIES = 33


def create_game(client: TestClient) -> dict[str, Any]:
    body = {"pgn": read_pgn("opera_game.pgn"), "user_color": "white"}
    response = client.post("/api/games", json=body)
    assert response.status_code == 201
    game: dict[str, Any] = response.json()
    return game


def scan_batch(game: dict[str, Any]) -> list[dict[str, Any]]:
    fens = [p["fen_before"] for p in game["positions"]]
    if not game["final_is_terminal"]:
        fens.append(game["final_fen"])
    return [fake_result(fen, "scan", plies=1) for fen in fens]


def post(client: TestClient, game: dict[str, Any], tier: str, results: list[Any]) -> Any:
    return client.post(f"/api/games/{game['game_id']}/engine/{tier}", json={"results": results})


def test_engine_config_serves_the_tiers(client: TestClient) -> None:
    response = client.get("/api/engine-config")

    assert response.status_code == 200
    data = response.json()
    assert data["scan"] == {
        "multipv": 1,
        "min_time_ms": 250,
        "min_depth": 12,
        "hard_cap_ms": 1000,
        "max_line_plies": 1,
    }
    assert (data["verify"]["multipv"], data["deep"]["hard_cap_ms"]) == (4, 8000)
    assert (data["max_threads"], data["hash_mb"]) == (4, 64)


def test_scan_then_verify_round_trip(client: TestClient, db_session: Session) -> None:
    game = create_game(client)

    scan = post(client, game, "scan", scan_batch(game))

    assert scan.status_code == 200
    verify_fens = scan.json()["verify_fens"]
    # Flat 0.0 evals, but the final checkmate is scored from the board (+M0), so the biggest
    # swing is the mating move (ply 33); ties for the other two go to the earliest plies (1, 2).
    positions = game["positions"]
    assert verify_fens == [positions[i]["fen_before"] for i in (0, 1, 2, 32)]

    verify_batch = [fake_result(fen, "verify", lines=4, plies=10) for fen in verify_fens]
    verify = post(client, game, "verify", verify_batch)

    assert verify.status_code == 200
    data = verify.json()
    assert data["summary_ready"] is True
    assert data["counts"] == {"inaccuracies": 0, "mistakes": 0, "blunders": 0, "missed_mates": 0}
    assert set(data["accuracy"]) == {"user", "opponent"}
    tiers = [row.tier for row in db_session.query(EngineResultRow).all()]
    assert (tiers.count("scan"), tiers.count("verify")) == (OPERA_PLIES, 4)
    summary = load_summary(db_session, game["game_id"])
    assert summary is not None
    assert len(summary.move_list) == OPERA_PLIES


def test_status_moves_through_scanned_to_analyzed_and_results_belong_to_the_player(
    client: TestClient, db_session: Session
) -> None:
    game = create_game(client)
    row = db_session.get(Game, game["game_id"])
    assert row is not None and row.status == "uploaded"

    verify_fens = post(client, game, "scan", scan_batch(game)).json()["verify_fens"]
    db_session.refresh(row)
    assert row.status == "scanned"
    post(client, game, "verify", [fake_result(f, "verify", lines=4, plies=10) for f in verify_fens])

    db_session.refresh(row)
    assert row.status == "analyzed"
    owners = {result.user_id for result in db_session.query(EngineResultRow).all()}
    assert owners == {row.user_id} and row.user_id is not None


def test_scan_flags_the_users_blunder(client: TestClient) -> None:
    game = create_game(client)
    batch = scan_batch(game)
    for result in batch[11:]:  # White's move at ply 11 drops the eval from 0.0 to -5.0
        result["lines"][0]["eval_cp"] = -500

    fens = post(client, game, "scan", batch).json()["verify_fens"]

    assert game["positions"][10]["fen_before"] in fens  # before ply 11
    assert game["positions"][11]["fen_before"] in fens  # after ply 11


def test_resubmitting_a_scan_replaces_earlier_results(
    client: TestClient, db_session: Session
) -> None:
    game = create_game(client)

    post(client, game, "scan", scan_batch(game))
    post(client, game, "scan", scan_batch(game))

    assert db_session.query(EngineResultRow).count() == OPERA_PLIES


def test_incomplete_scan_is_rejected(client: TestClient) -> None:
    game = create_game(client)

    response = post(client, game, "scan", scan_batch(game)[:-1])

    assert response.status_code == 422
    assert response.json()["detail"] == "Missing engine results for 1 position(s)."


def test_verify_before_scan_is_a_conflict(client: TestClient) -> None:
    game = create_game(client)

    assert post(client, game, "verify", []).status_code == 409


def test_verify_must_match_the_selected_positions(client: TestClient) -> None:
    game = create_game(client)
    post(client, game, "scan", scan_batch(game))
    wrong = [fake_result(game["positions"][20]["fen_before"], "verify")]

    assert post(client, game, "verify", wrong).status_code == 422


def test_unknown_game_is_not_found(client: TestClient) -> None:
    response = client.post("/api/games/nope/engine/scan", json={"results": []})

    assert response.status_code == 404


def test_malformed_engine_result_is_rejected(client: TestClient) -> None:
    game = create_game(client)
    batch = scan_batch(game)
    batch[0]["lines"][0]["mate"] = 3  # both eval_cp and mate set

    assert post(client, game, "scan", batch).status_code == 422
