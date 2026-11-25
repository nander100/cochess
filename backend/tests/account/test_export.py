"""Data export (SPEC_V4 §11, §14.3): one zip with everything that's the player's, the games as
annotated PGNs that re-import to the same games, only their own data, and not too often."""

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Any

import chess.pgn
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.billing.ledger import adjust_by_owner
from app.config import Limits, Settings
from app.db.chat import save_turn
from app.db.models import Game, User
from app.main import create_app
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import BASE_URL, log_in
from tests.coach_fakes import FakeCoachClient
from tests.databases import fresh_database_url


@pytest.fixture
def app() -> FastAPI:
    return create_app(
        Settings(_env_file=None, database_url=fresh_database_url()), FakeCoachClient()
    )


def _zip(response: Any) -> zipfile.ZipFile:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(response.content))


def _chat(app: FastAPI, game_id: str) -> None:
    with app.state.session_factory() as session:
        save_turn(session, game_id, "user", [{"type": "text", "text": "Why?"}], display="Why?")
        save_turn(
            session, game_id, "assistant", [{"type": "text", "text": "x"}],
            display="Because [rook takes on d7](cc:move/0) opened the king.",
        )  # fmt: skip


def test_the_zip_holds_profile_settings_games_chats_and_credits(app: FastAPI) -> None:
    client = log_in(app, "Exporter", metered=True)
    client.patch("/api/settings", json={"theme": "dark"})
    with app.state.session_factory() as session:
        user = session.scalars(select(User).where(User.name == "Exporter")).one()
        adjust_by_owner(session, user, 250_000, note="welcome", now=datetime.now(UTC))
        session.commit()
    game_id = analyzed_game(client, "white")
    _chat(app, game_id)

    archive = _zip(client.post("/api/me/export"))

    names = archive.namelist()
    assert "README.txt" in names
    profile = json.loads(archive.read("profile.json"))
    assert profile["name"] == "Exporter" and profile["elo"] == 1350
    assert json.loads(archive.read("settings.json"))["theme"] == "dark"
    [pgn_name] = [n for n in names if n.startswith("games/")]
    assert pgn_name.endswith(".pgn")
    [coaching] = [n for n in names if n.startswith("coaching/")]
    text = archive.read(coaching).decode()
    assert "Why?" in text and "Because rook takes on d7 opened the king." in text
    assert "cc:move" not in text
    rows = list(csv.DictReader(io.StringIO(archive.read("credits.csv").decode())))
    assert [(r["kind"], r["credits"], r["note"]) for r in rows] == [
        ("owner_grant", "25", "welcome")
    ]


def test_the_exported_games_reimport_as_the_same_games(app: FastAPI) -> None:
    client = log_in(app, "Exporter")
    game_id = analyzed_game(client, "black")
    with app.state.session_factory() as session:
        game = session.get(Game, game_id)
        assert game is not None
        original = chess.pgn.read_game(io.StringIO(game.pgn))
    assert original is not None

    archive = _zip(client.post("/api/me/export"))
    [name] = [n for n in archive.namelist() if n.startswith("games/")]
    exported = chess.pgn.read_game(io.StringIO(archive.read(name).decode()))

    assert exported is not None
    assert [m.uci() for m in exported.mainline_moves()] == [
        m.uci() for m in original.mainline_moves()
    ]
    for header in ("White", "Black", "Result"):
        assert exported.headers[header] == original.headers[header]
    body = {"pgn": archive.read(name).decode(), "user_color": "black"}
    assert client.post("/api/games", json=body).status_code == 409  # the same game


def test_only_the_players_own_data_is_exported(app: FastAPI) -> None:
    mine, theirs = log_in(app, "Mine"), log_in(app, "Theirs")
    analyzed_game(theirs, "white")
    _chat(app, analyzed_game(theirs, "black", "annotated_clock_game.pgn"))

    archive = _zip(mine.post("/api/me/export"))

    assert not [n for n in archive.namelist() if n.startswith(("games/", "coaching/"))]
    assert b"Theirs" not in b"".join(archive.read(n) for n in archive.namelist())


def test_a_second_export_soon_after_is_refused() -> None:
    settings = Settings(
        _env_file=None,
        database_url=fresh_database_url(),
        limits=Limits(export_cooldown_seconds=600),
    )
    client = log_in(create_app(settings, FakeCoachClient()), "Eager")

    assert client.post("/api/me/export").status_code == 200
    again = client.post("/api/me/export")

    assert again.status_code == 429
    assert "minutes" in again.json()["detail"]


def test_a_paused_account_can_still_export(app: FastAPI) -> None:
    client = log_in(app, "Paused")
    with app.state.session_factory() as session:
        session.scalars(select(User).where(User.name == "Paused")).one().status = "suspended"
        session.commit()

    assert client.post("/api/me/export").status_code == 200


def test_export_needs_a_login(app: FastAPI) -> None:
    assert TestClient(app, base_url=BASE_URL).post("/api/me/export").status_code == 401
