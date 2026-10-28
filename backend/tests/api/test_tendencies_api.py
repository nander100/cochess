"""GET /api/tendencies and the snapshot after each analyzed game (SPEC_V2 §9)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GameThemeFactRow, TendencySnapshotRow, User
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import log_in


def test_empty_before_the_first_analyzed_game(client: TestClient) -> None:
    response = client.get("/api/tendencies")

    assert response.status_code == 200
    assert response.json() == {
        "games_analyzed": 0,
        "provisional": True,
        "tendencies": [],
        "accuracy": {
            "overall": None,
            "by_color": {"white": None, "black": None},
            "by_phase": {"opening": None, "middlegame": None, "endgame": None},
        },
    }


def test_an_analyzed_game_stores_its_facts_and_a_snapshot(
    client: TestClient, db_session: Session
) -> None:
    game_id = analyzed_game(client)

    facts = list(db_session.scalars(select(GameThemeFactRow)))
    snapshots = list(db_session.scalars(select(TendencySnapshotRow)))
    user = db_session.scalars(select(User)).one()
    assert facts and {(f.game_id, f.user_id, f.user_color) for f in facts} == {
        (game_id, user.id, "white")
    }
    assert [s.games_analyzed for s in snapshots] == [1]
    report = client.get("/api/tendencies").json()
    assert report["games_analyzed"] == 1
    assert report["provisional"] is True
    assert report["accuracy"]["by_color"]["black"] is None


def test_each_analyzed_game_adds_a_snapshot(client: TestClient, db_session: Session) -> None:
    analyzed_game(client)
    analyzed_game(client, "annotated_clock_game.pgn")

    snapshots = db_session.scalars(select(TendencySnapshotRow.games_analyzed)).all()
    assert sorted(snapshots) == [1, 2]
    assert client.get("/api/tendencies").json()["games_analyzed"] == 2


def test_tendencies_are_only_the_players_own(app: FastAPI, client: TestClient) -> None:
    analyzed_game(client)
    other = log_in(app, "Someone else")

    assert other.get("/api/tendencies").json()["games_analyzed"] == 0
