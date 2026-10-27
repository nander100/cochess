"""Alembic migrations: a fresh database and a v1 database both end at the models' schema."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

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
        for game_id in ("g1", "g2"):
            connection.execute(
                text(
                    "INSERT INTO games (id, pgn, user_color, elo, playstyle, headers, created_at) "
                    f"VALUES ('{game_id}', '1. e4 *', 'white', 1400, NULL, '{{}}', "
                    "'2026-10-01 12:00:00')"
                )
            )
        connection.execute(
            text(
                "INSERT INTO game_summaries (game_id, summary, created_at) "
                "VALUES ('g1', '{}', '2026-10-01 12:01:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO engine_results (game_id, ply, fen, tier, depth, time_ms, lines, "
                "created_at) VALUES ('g1', 1, "
                "'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 'scan', 12, 250, "
                "'[]', '2026-10-01 12:00:30')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO llm_usage (game_id, endpoint, model, input_tokens, output_tokens, "
                "cache_read_tokens, cache_write_tokens, created_at) "
                "VALUES ('g1', 'synopsis', 'm', 1, 1, 0, 0, '2026-10-01 12:02:00')"
            )
        )

    upgrade(engine)

    assert _version(engine) == _head()
    assert _differences(engine) == []
    with engine.connect() as connection:
        games = connection.execute(text("SELECT id, elo, status, user_id FROM games ORDER BY id"))
        assert games.all() == [("g1", 1400, "analyzed", None), ("g2", 1400, "uploaded", None)]
        assert connection.execute(text("SELECT task FROM llm_usage")).scalar() == "synopsis"
        key = connection.execute(text("SELECT position_key FROM engine_results")).scalar()
        assert key == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


def test_every_migration_downgrades_back_to_an_empty_database() -> None:
    engine = make_engine("sqlite://")
    upgrade(engine)
    config = alembic_config()

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")

    assert _differences(engine) == []
