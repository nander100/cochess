"""GET /api/dashboard (SPEC_V3 §8.1): one response from stored numbers, filtered, per player,
fast for 200 games."""

import time
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analysis.tendencies import AccuracyReport, Example, Tendency, TendencyReport
from app.config import Settings
from app.db.models import Game, GameStatsRow, TendencySnapshotRow, User
from app.main import create_app
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import log_in


def test_a_new_player_sees_an_empty_dashboard(client: TestClient) -> None:
    body = client.get("/api/dashboard").json()

    assert body["games"] == 0 and body["recent"] == [] and body["focus_areas"] == []
    assert body["onboarding"] == {
        "complete": False,
        "analyzed": 0,
        "total": 12,
        "has_report": False,
    }


def test_analyzed_games_show_with_their_numbers(app: FastAPI, client: TestClient) -> None:
    white = analyzed_game(client, "white")

    body = client.get("/api/dashboard").json()

    [recent] = body["recent"]
    assert (recent["game_id"], recent["color"], recent["opponent"]) == (
        white,
        "white",
        "Duke Karl / Count Isouard",
    )
    assert recent["accuracy"] is not None
    assert len(body["accuracy"]["points"]) == 1
    assert set(body["accuracy"]["by_phase"]) == {"opening", "middlegame", "endgame"}
    with app.state.session_factory() as session:
        assert session.get(GameStatsRow, white) is not None  # written with the summary


def test_filters_narrow_the_games(client: TestClient) -> None:
    analyzed_game(client, "white")

    assert client.get("/api/dashboard?color=white").json()["games"] == 1
    assert client.get("/api/dashboard?color=black").json()["games"] == 0
    assert client.get("/api/dashboard?tc=bullet").json()["games"] == 0
    assert client.get("/api/dashboard?range=10").json()["games"] == 1
    assert client.get("/api/dashboard?range=7").status_code == 422
    assert client.get("/api/dashboard?color=red").status_code == 422


def test_each_player_sees_only_their_own_games(app: FastAPI, client: TestClient) -> None:
    analyzed_game(client, "white")

    assert log_in(app, "Other").get("/api/dashboard").json()["games"] == 0


def test_games_analyzed_before_game_stats_get_them_once(app: FastAPI, client: TestClient) -> None:
    game_id = analyzed_game(client, "white")
    with app.state.session_factory() as session:
        session.query(GameStatsRow).delete()
        session.commit()

    assert client.get("/api/dashboard").json()["games"] == 1

    with app.state.session_factory() as session:
        assert session.get(GameStatsRow, game_id) is not None


def test_the_dashboard_needs_a_login(anon_client: TestClient) -> None:
    assert anon_client.get("/api/dashboard").status_code == 401


def _tendency(theme: str, score: float, game_id: str) -> Tendency:
    return Tendency.model_validate(
        {
            "theme": theme, "label": theme, "rate_per_game": score, "score": score,
            "trend": "steady", "games_seen": 50, "provisional": False,
            "recent_example": Example(game_id=game_id, move_number=12, move_san="Nf3"),
        }
    )  # fmt: skip


def test_two_hundred_games_load_within_the_target() -> None:
    app = create_app(Settings(_env_file=None, database_url="sqlite://"))
    client = log_in(app, "Busy player")
    start = datetime(2025, 1, 1, tzinfo=UTC)
    themes = ["hung_piece", "missed_tactic", "king_safety", "allowed_tactic", "pawn_structure",
              "endgame_technique", "time_trouble", "slow_development"]  # fmt: skip
    with app.state.session_factory() as session:
        user = session.query(User).one()
        for n in range(200):
            game = Game(
                user_id=user.id, pgn="1. e4 e5 *", user_color="white" if n % 2 else "black",
                elo=1400, headers={"White": "Me", "Black": f"Rival {n}"}, status="analyzed",
                time_control_category="rapid", user_result="win" if n % 3 else "loss",
                played_at=start + timedelta(days=n), fingerprint=f"fp{n}",
            )  # fmt: skip
            session.add(game)
            session.flush()
            session.add(GameStatsRow(game_id=game.id, user_id=user.id, accuracy=70.0 + n % 20,
                                     accuracy_opening=80.0, accuracy_middlegame=70.0,
                                     accuracy_endgame=60.0, moments_total=3))  # fmt: skip
            report = TendencyReport(
                games_analyzed=n + 1, provisional=False,
                tendencies=[_tendency(t, 3.0 - i * 0.3, game.id) for i, t in enumerate(themes)],
                accuracy=AccuracyReport(overall=75.0, by_color={}, by_phase={}),
            )  # fmt: skip
            session.add(
                TendencySnapshotRow(
                    user_id=user.id, games_analyzed=n + 1, report=report.model_dump(mode="json"),
                    created_at=start + timedelta(days=n),
                )
            )  # fmt: skip
        session.commit()
    client.get("/api/dashboard")  # warm up

    began = time.perf_counter()
    response = client.get("/api/dashboard")
    elapsed = time.perf_counter() - began

    assert response.status_code == 200
    body = response.json()
    assert body["games"] == 200 and len(body["mistake_trend"]["points"]) == 200
    assert len(body["focus_areas"]) == 3 and len(body["recent"]) == 10
    assert elapsed < 0.3, f"took {elapsed * 1000:.0f} ms"
