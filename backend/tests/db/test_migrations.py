"""Alembic migrations: a fresh database and a v1 database both end at the models' schema."""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from app.db.migrate import alembic_config, upgrade
from app.db.models import Base
from app.db.session import make_engine

V1_SCHEMA = Path(__file__).parents[1] / "fixtures" / "v1_schema.sql"


def _head() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head


def _differences(engine: Engine) -> list[object]:
    with engine.connect() as connection:
        return list(compare_metadata(MigrationContext.configure(connection), Base.metadata))


def _version(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def test_fresh_database_matches_the_models() -> None:
    engine = make_engine("sqlite://")

    upgrade(engine)

    assert _version(engine) == _head()
    assert _differences(engine) == []


def test_upgrade_is_idempotent() -> None:
    engine = make_engine("sqlite://")
    upgrade(engine)

    upgrade(engine)

    assert _version(engine) == _head()


def test_v1_database_is_stamped_then_upgraded_and_keeps_its_data() -> None:
    engine = make_engine("sqlite://")
    with engine.begin() as connection:
        for statement in V1_SCHEMA.read_text().split(";"):
            if statement.strip():
                connection.execute(text(statement))
        connection.execute(
            text(
                "INSERT INTO games (id, pgn, user_color, elo, playstyle, headers, created_at) "
                "VALUES ('g1', '1. e4 *', 'white', 1400, NULL, '{}', '2026-10-01 12:00:00')"
            )
        )

    upgrade(engine)

    assert _version(engine) == _head()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id, elo FROM games")).all() == [("g1", 1400)]
