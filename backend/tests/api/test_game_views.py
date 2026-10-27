"""GET /api/games (My games) and GET /api/games/{id} (the analysis board's data)."""

import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.chat import save_turn
from app.db.coach import save_synopsis
from app.db.engine_results import load_summary, save_summary
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import log_in
from tests.engine_fakes import fake_result
from tests.pgn_fixtures import read_pgn

OPERA_PLIES = 33


def _upload(client: TestClient, pgn: str, color: str = "white") -> dict[str, Any]:
    response = client.post("/api/games", json={"pgn": pgn, "user_color": color})
    assert response.status_code == 201, response.text
    game: dict[str, Any] = response.json()
    return game


def _pgn(date: str, white: str, black: str) -> str:
    return f'[Date "{date}"]\n[White "{white}"]\n[Black "{black}"]\n[Result "1-0"]\n\n1. e4 1-0'


def _scan(client: TestClient, game: dict[str, Any]) -> list[str]:
    fens = [p["fen_before"] for p in game["positions"]]
    if not game["final_is_terminal"]:
        fens.append(game["final_fen"])
    results = [fake_result(fen, "scan", plies=1) for fen in fens]
    response = client.post(f"/api/games/{game['game_id']}/engine/scan", json={"results": results})
    verify: list[str] = response.json()["verify_fens"]
    return verify


class TestMyGames:
    def test_lists_only_my_games_most_recently_played_first(self, app: FastAPI) -> None:
        me, other = log_in(app, "Me"), log_in(app, "Other")
        _upload(me, _pgn("2026.03.01", "Me", "Old Rival"))
        _upload(me, _pgn("2026.05.01", "Newer", "Me"), "black")
        _upload(other, "1. d4 *")

        games = me.get("/api/games").json()

        assert [(g["opponent"], g["user_color"], g["user_result"]) for g in games] == [
            ("Newer", "black", "loss"),
            ("Old Rival", "white", "win"),
        ]
        assert games[0]["played_at"].startswith("2026-05-01")
        assert len(other.get("/api/games").json()) == 1

    def test_an_analyzed_game_shows_accuracy_and_status(self, client: TestClient) -> None:
        analyzed_game(client)

        (game,) = client.get("/api/games").json()

        assert game["status"] == "analyzed"
        assert isinstance(game["accuracy"], float)
        assert game["opening"] == "Philidor Defense"  # from the Opening header


class TestGameDetail:
    def test_an_analyzed_game_has_moves_evals_labels_and_engine_lines(
        self, client: TestClient
    ) -> None:
        game_id = analyzed_game(client)

        detail = client.get(f"/api/games/{game_id}").json()

        assert detail["status"] == "analyzed"
        assert detail["user_color"] == "white" and detail["elo"] == 1350
        moves = detail["moves"]
        assert len(moves) == OPERA_PLIES
        assert moves[0] | {"clock_s": None} == {
            "ply": 1,
            "move_number": 1,
            "side": "white",
            "san": "e4",
            "uci": "e2e4",
            "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "clock_s": None,
            "eval_after": "0.0",  # the fake engine scores every position 0.0
            "win_pct_after": 50.0,
            "label": None,
        }
        assert detail["start_win_pct"] == 50.0
        # The final position is checkmate, scored from the board: White's win% is 100.
        assert (moves[-1]["san"], moves[-1]["eval_after"], moves[-1]["win_pct_after"]) == (
            "Rd8#",
            "+M0",
            100.0,
        )
        assert detail["final_is_terminal"] is True
        assert detail["info"]["white"] == "Paul Morphy"
        assert set(detail["accuracy"]) == {"user", "opponent"}
        verified = [r for r in detail["engine_results"] if r["tier"] == "verify"]
        assert verified and len(verified[0]["lines"]) == 4
        line = verified[0]["lines"][0]
        assert len(line["moves_san"]) == len(line["moves_uci"]) and line["eval"] == "0.0"
        assert detail["verify_fens"] == [] and detail["synopsis"] is None and detail["chat"] == []

    def test_labels_come_from_the_summary(self, client: TestClient, db_session: Session) -> None:
        game_id = analyzed_game(client)
        summary = load_summary(db_session, game_id)
        assert summary is not None
        moves = [m.model_copy(update={"classification": "blunder"}) if m.ply == 3 else m
                 for m in summary.move_list]  # fmt: skip
        save_summary(db_session, game_id, summary.model_copy(update={"move_list": moves}))

        labels = [m["label"] for m in client.get(f"/api/games/{game_id}").json()["moves"]]

        assert labels[2] == "blunder" and labels.count(None) == OPERA_PLIES - 1

    def test_an_uploaded_game_has_moves_but_no_evals_yet(self, client: TestClient) -> None:
        game = _upload(client, read_pgn("opera_game.pgn"))

        detail = client.get(f"/api/games/{game['game_id']}").json()

        assert detail["status"] == "uploaded"
        assert len(detail["moves"]) == OPERA_PLIES
        assert {m["win_pct_after"] for m in detail["moves"]} == {None}
        assert detail["start_win_pct"] is None and detail["accuracy"] is None
        assert detail["engine_results"] == [] and detail["verify_fens"] == []

    def test_a_scanned_game_lists_the_positions_still_to_verify(self, client: TestClient) -> None:
        game = _upload(client, read_pgn("opera_game.pgn"))
        expected = _scan(client, game)

        detail = client.get(f"/api/games/{game['game_id']}").json()

        assert detail["status"] == "scanned"
        assert detail["verify_fens"] == expected and expected
        assert detail["moves"][0]["win_pct_after"] == 50.0  # scan evals are already shown

    def test_shows_the_synopsis_and_the_chat_as_the_player_saw_it(
        self, client: TestClient, db_session: Session
    ) -> None:
        game_id = analyzed_game(client)
        save_synopsis(db_session, game_id, "### Overall\nA tidy game.", ["Nf9"])
        payload = {"task": "chat", "user_prompt": "What if I take on e5?"}
        rendered = f"The player's new chat message, as JSON.\n\n{json.dumps(payload)}"
        turns: list[tuple[str, list[dict[str, Any]]]] = [
            ("user", [{"type": "text", "text": rendered}]),
            ("assistant", [{"type": "thinking", "thinking": "...", "signature": "s"},
                           {"type": "text", "text": "Let me check."},
                           {"type": "tool_use", "id": "t1", "name": "analyze_position",
                            "input": {"ply": 3}}]),
            ("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]),
            ("assistant", [{"type": "text", "text": "The engine says it loses a pawn."}]),
        ]  # fmt: skip
        for role, blocks in turns:
            save_turn(db_session, game_id, role, blocks)

        detail = client.get(f"/api/games/{game_id}").json()

        assert detail["synopsis"] == {
            "text": "### Overall\nA tidy game.",
            "invalid_moves_removed": ["Nf9"],
        }
        assert detail["chat"] == [
            {"role": "player", "text": "What if I take on e5?"},
            {"role": "coach", "text": "The engine says it loses a pawn."},
        ]

    def test_needs_a_login_and_the_owner(self, app: FastAPI, client: TestClient) -> None:
        game_id = analyzed_game(client)

        assert log_in(app, "Other").get(f"/api/games/{game_id}").status_code == 404
        assert client.get("/api/games/nope").status_code == 404
