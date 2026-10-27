import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.service import redeem_invite
from app.cli import main
from app.config import Settings
from app.db.models import EngineResultRow, Game, User
from app.db.session import make_engine


@pytest.fixture
def file_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'cli.db'}",
        public_base_url="https://cochess.example/",
    )


def _run(settings: Settings, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = main(list(argv), settings, out)
    return code, out.getvalue()


def _session(settings: Settings) -> Session:
    return sessionmaker(make_engine(settings.database_url), expire_on_commit=False)()


def test_create_user_then_refuse_a_duplicate(file_settings: Settings) -> None:
    assert _run(file_settings, "create-user", "--name", "Alex")[0] == 0

    code, _ = _run(file_settings, "create-user", "--name", "alex")

    assert code == 1
    with _session(file_settings) as session:
        assert [u.name for u in session.scalars(select(User))] == ["Alex"]


def test_invite_prints_a_one_time_link_with_the_token_in_the_fragment(
    file_settings: Settings,
) -> None:
    _run(file_settings, "create-user", "--name", "Alex")

    code, output = _run(file_settings, "invite", "--user", "ALEX")

    assert code == 0
    link = output.strip().splitlines()[-1]
    assert link.startswith("https://cochess.example/redeem#token=")
    token = link.split("#token=", 1)[1]
    with _session(file_settings) as session:
        assert redeem_invite(session, token, datetime.now(UTC), file_settings.auth)


def test_invite_for_an_unknown_user_fails(file_settings: Settings) -> None:
    assert _run(file_settings, "invite", "--user", "Nobody")[0] == 1


def test_assign_games_gives_v1_games_to_the_user_with_date_and_result(
    file_settings: Settings,
) -> None:
    _run(file_settings, "create-user", "--name", "Alex")
    uploaded = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    with _session(file_settings) as session:
        session.add_all(
            [
                Game(
                    id="dated",
                    pgn="1. e4 *",
                    user_color="black",
                    elo=1400,
                    headers={"UTCDate": "2026.10.01", "UTCTime": "18:04:05", "Result": "0-1"},
                    created_at=uploaded,
                ),
                Game(
                    id="undated",
                    pgn="1. e4 *",
                    user_color="white",
                    elo=1400,
                    headers={"Result": "*"},
                    created_at=uploaded,
                ),
                EngineResultRow(
                    game_id="dated",
                    fen="f",
                    position_key="f",
                    tier="scan",
                    depth=1,
                    time_ms=1,
                    lines=[],
                ),
            ]
        )
        session.commit()

    code, output = _run(file_settings, "assign-games", "--user", "Alex")

    assert code == 0
    assert "Assigned 2 game(s) to Alex" in output
    with _session(file_settings) as session:
        user = session.scalars(select(User)).one()
        dated, undated = session.get(Game, "dated"), session.get(Game, "undated")
        assert dated is not None and undated is not None
        assert (dated.user_id, dated.user_result) == (user.id, "win")
        assert dated.played_at == datetime(2026, 10, 1, 18, 4, 5, tzinfo=UTC)
        assert (undated.user_result, undated.played_at) == (None, uploaded)
        assert session.scalars(select(EngineResultRow.user_id)).one() == user.id
    assert "Assigned 0 game(s)" in _run(file_settings, "assign-games", "--user", "Alex")[1]
