"""Change color and delete game (PLAN_V3 M1): fixing a game analyzed from the wrong side."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ChatMessageRow,
    EngineResultRow,
    Game,
    GameSummaryRow,
    GameThemeFactRow,
    LlmUsageRow,
    MomentProgressRow,
)
from tests.auth_helpers import log_in
from tests.engine_fakes import fake_result
from tests.pgn_fixtures import read_pgn

OPERA = read_pgn("opera_game.pgn")


def _cp(index: int) -> int:
    """White-POV evals that rise after every Black move: Black's moves are the mistakes, so
    playing Black needs positions verified that playing White didn't."""
    return 150 * (index // 2)


def _analyzed(client: TestClient, color: str, pgn: str = OPERA) -> dict[str, Any]:
    created = client.post("/api/games", json={"pgn": pgn, "user_color": color})
    assert created.status_code == 201, created.text
    game: dict[str, Any] = created.json()
    fens = [p["fen_before"] for p in game["positions"]]
    if not game["final_is_terminal"]:
        fens.append(game["final_fen"])
    scan = [fake_result(f, "scan", cp=_cp(i), plies=1) for i, f in enumerate(fens)]
    verify_fens = client.post(
        f"/api/games/{game['game_id']}/engine/scan", json={"results": scan}
    ).json()["verify_fens"]
    _verify(client, game["game_id"], verify_fens)
    game["verified"] = verify_fens
    return game


def _verify(client: TestClient, game_id: str, fens: list[str]) -> None:
    by_index = {f: i for i, f in enumerate(_scan_order(client, game_id))}
    results = [fake_result(f, "verify", cp=_cp(by_index[f]), lines=4, plies=10) for f in fens]
    response = client.post(f"/api/games/{game_id}/engine/verify", json={"results": results})
    assert response.status_code == 200, response.text


def _scan_order(client: TestClient, game_id: str) -> list[str]:
    detail = client.get(f"/api/games/{game_id}").json()
    return [m["fen_before"] for m in detail["moves"]] + [detail["final_fen"]]


def _count(session: Session, table: Any, game_id: str) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).where(table.game_id == game_id)) or 0


class TestChangeColor:
    def test_the_new_side_tops_up_only_the_missing_positions_then_is_analyzed(
        self, client: TestClient
    ) -> None:
        game = _analyzed(client, "white")
        game_id = game["game_id"]

        response = client.patch(f"/api/games/{game_id}", json={"user_color": "black"})

        assert response.status_code == 200, response.text
        detail = response.json()
        assert detail["user_color"] == "black"
        assert detail["status"] == "scanned"
        assert detail["accuracy"] is None
        assert detail["verify_fens"]
        assert not set(detail["verify_fens"]) & set(game["verified"])

        _verify(client, game_id, detail["verify_fens"])

        after = client.get(f"/api/games/{game_id}").json()
        assert after["status"] == "analyzed"
        assert after["verify_fens"] == []
        assert after["accuracy"]["user"] is not None

    def test_a_game_with_everything_verified_is_rebuilt_at_once(self, client: TestClient) -> None:
        game = _analyzed(client, "black")
        game_id = game["game_id"]

        detail = client.patch(f"/api/games/{game_id}", json={"user_color": "white"}).json()

        # White needs a subset of what Black's analysis already verified.
        assert detail["status"] == "analyzed"
        assert detail["user_color"] == "white"
        assert detail["verify_fens"] == []

    def test_coaching_about_the_old_side_is_cleared(
        self, client: TestClient, db_session: Session
    ) -> None:
        game_id = _analyzed(client, "white")["game_id"]
        db_session.add_all(
            [
                ChatMessageRow(game_id=game_id, role="assistant", content={"type": "synopsis"}),
                MomentProgressRow(
                    user_id=db_session.get(Game, game_id).user_id,  # type: ignore[union-attr]
                    game_id=game_id,
                    moment_index=1,
                    state="attempt",
                    attempts=[],
                    messages=[],
                ),
            ]
        )
        db_session.commit()

        client.patch(f"/api/games/{game_id}", json={"user_color": "black"})

        assert _count(db_session, ChatMessageRow, game_id) == 0
        assert _count(db_session, MomentProgressRow, game_id) == 0
        assert _count(db_session, EngineResultRow, game_id) > 0  # engine work is reused

    def test_the_result_follows_the_color(self, client: TestClient) -> None:
        game_id = _analyzed(client, "white")["game_id"]  # the Opera game: White won

        client.patch(f"/api/games/{game_id}", json={"user_color": "black"})

        listed = client.get("/api/games").json()[0]
        assert (listed["user_color"], listed["user_result"]) == ("black", "loss")

    def test_the_same_color_changes_nothing(self, client: TestClient) -> None:
        game_id = _analyzed(client, "white")["game_id"]

        detail = client.patch(f"/api/games/{game_id}", json={"user_color": "white"}).json()

        assert (detail["user_color"], detail["status"]) == ("white", "analyzed")

    @pytest.mark.parametrize("body", [{}, {"user_color": "red"}, {"user_color": None}])
    def test_a_color_is_required(self, client: TestClient, body: dict[str, Any]) -> None:
        game_id = _analyzed(client, "white")["game_id"]

        response = client.patch(f"/api/games/{game_id}", json=body)

        assert response.status_code == 422
        assert response.json()["detail"][0]["msg"] == (
            "Choose the color you played: White or Black."
        )


class TestDelete:
    def test_the_game_and_everything_stored_for_it_go(
        self, client: TestClient, db_session: Session
    ) -> None:
        game_id = _analyzed(client, "white")["game_id"]
        user_id = db_session.get(Game, game_id).user_id  # type: ignore[union-attr]
        db_session.add(LlmUsageRow(game_id=game_id, user_id=user_id, endpoint="chat",
                                   task="chat", model="m", input_tokens=10, output_tokens=5,
                                   cache_read_tokens=0, cache_write_tokens=0))  # fmt: skip
        db_session.commit()
        assert client.get("/api/tendencies").json()["games_analyzed"] == 1

        response = client.delete(f"/api/games/{game_id}")

        assert response.status_code == 204
        assert client.get(f"/api/games/{game_id}").status_code == 404
        assert client.get("/api/games").json() == []
        for table in (EngineResultRow, GameSummaryRow, GameThemeFactRow, ChatMessageRow):
            assert _count(db_session, table, game_id) == 0
        usage = db_session.scalars(select(LlmUsageRow).where(LlmUsageRow.user_id == user_id))
        assert [row.game_id for row in usage] == [None]  # still counts toward the budget
        assert client.get("/api/tendencies").json()["games_analyzed"] == 0

    def test_a_deleted_game_can_be_uploaded_again(self, client: TestClient) -> None:
        game_id = _analyzed(client, "white")["game_id"]
        client.delete(f"/api/games/{game_id}")

        response = client.post("/api/games", json={"pgn": OPERA, "user_color": "black"})

        assert response.status_code == 201


class TestIsolation:
    def test_another_players_game_is_not_found(self, app: FastAPI, client: TestClient) -> None:
        game_id = _analyzed(client, "white")["game_id"]
        other = log_in(app, "Other")

        assert other.patch(f"/api/games/{game_id}", json={"user_color": "black"}).status_code == 404
        assert other.delete(f"/api/games/{game_id}").status_code == 404
        assert client.get(f"/api/games/{game_id}").json()["user_color"] == "white"

    def test_changes_need_a_login(self, anon_client: TestClient) -> None:
        assert anon_client.patch("/api/games/x", json={"user_color": "black"}).status_code == 401
        assert anon_client.delete("/api/games/x").status_code == 401


ME = "nander100"


def _onboarding_pgn(n: int, color: str, result: str) -> str:
    white, black = (ME, f"Opponent {n}") if color == "white" else (f"Opponent {n}", ME)
    return (
        f'[White "{white}"]\n[Black "{black}"]\n[Result "{result}"]\n[TimeControl "600"]\n\n'
        f"1. e4 e5 2. Nf3 Nc6 {result}"
    )


def _submit(client: TestClient, games: list[tuple[str, str]]) -> list[str]:
    body = {"games": [{"pgn": pgn, "user_color": color} for pgn, color in games]}
    response = client.post("/api/onboarding/submit", json=body)
    assert response.status_code == 200, response.text
    return [r["game_id"] for r in response.json()["results"]]


class TestOnboardingGames:
    def test_deleting_an_onboarding_game_frees_its_slot(self, client: TestClient) -> None:
        ids = _submit(client, [(_onboarding_pgn(i, "white", "1-0"), "white") for i in range(3)])

        client.delete(f"/api/games/{ids[0]}")

        slots = {
            s["slot"]: s["filled"] for s in client.get("/api/onboarding/status").json()["slots"]
        }
        assert slots["white_win"] == 2

    def test_a_color_change_into_a_full_slot_is_refused(self, client: TestClient) -> None:
        full = [(_onboarding_pgn(i, "black", "0-1"), "black") for i in range(3)]  # black wins
        ids = _submit(client, [*full, (_onboarding_pgn(9, "white", "0-1"), "white")])

        # 0-1 as White is a loss; as Black it would be a fourth Black win.
        response = client.patch(f"/api/games/{ids[3]}", json={"user_color": "black"})

        assert response.status_code == 409
        assert "four games in one assessment slot" in response.json()["detail"]

    def test_a_color_change_into_an_open_slot_moves_the_game(self, client: TestClient) -> None:
        ids = _submit(client, [(_onboarding_pgn(0, "white", "1-0"), "white")])

        assert client.patch(f"/api/games/{ids[0]}", json={"user_color": "black"}).status_code == 200

        slots = {
            s["slot"]: s["filled"] for s in client.get("/api/onboarding/status").json()["slots"]
        }
        assert (slots["white_win"], slots["black_loss"]) == (0, 1)
