"""Copying the v3 SQLite database into Postgres (SPEC_V4 §12.1, PLAN_V4 adjustment 5).

The source is a SQLite file filled through the API (an analyzed game: users, sessions, games,
engine results, summaries, stats, tendencies). The target is a fresh empty database: Postgres when
TEST_DATABASE_URL is set, otherwise another SQLite database, so the copy logic runs either way.
"""

import io
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, insert, inspect, select

from app.cli import main
from app.config import Settings
from app.db.copy_sqlite import CopyError, copy_database, find_problems
from app.db.migrate import upgrade
from app.db.models import Base, LlmUsageRow, User
from app.db.session import make_engine
from app.main import create_app
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import log_in
from tests.databases import fresh_database_url, is_postgres


def _usage(user_id: str, task: str) -> dict[str, object]:
    return {
        "user_id": user_id,
        "endpoint": task,
        "task": task,
        "model": "claude-haiku-5-5",
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }


def _filled_source(tmp_path: Path) -> tuple[str, Engine]:
    url = f"sqlite:///{tmp_path / 'v3.db'}"
    app = create_app(Settings(_env_file=None, database_url=url))
    analyzed_game(log_in(app, "Alex"), "white")
    engine = make_engine(url)
    with engine.begin() as connection:
        user_id = connection.execute(select(User.id)).scalar_one()
        connection.execute(insert(LlmUsageRow).values(**_usage(user_id, "synopsis")))
    return url, engine


def _empty_target() -> Engine:
    return make_engine(fresh_database_url(migrated=False))


def _count(engine: Engine, table_name: str) -> int:
    table = Base.metadata.tables[table_name]
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def test_every_row_is_copied_and_each_table_compares_equal(tmp_path: Path) -> None:
    _, source = _filled_source(tmp_path)
    target = _empty_target()

    results = copy_database(source, target)

    by_table = {r.table: r for r in results}
    assert set(by_table) == set(Base.metadata.tables)
    assert all(r.source_rows == r.target_rows for r in results)
    assert all(r.source_checksum == r.target_checksum for r in results)
    for name in ("users", "games", "engine_results", "game_summaries", "llm_usage"):
        assert by_table[name].target_rows == _count(source, name) > 0


def test_new_rows_after_the_copy_get_fresh_ids(tmp_path: Path) -> None:
    _, source = _filled_source(tmp_path)
    target = _empty_target()
    copy_database(source, target)

    with target.begin() as connection:
        user_id = connection.execute(select(User.id)).scalar_one()
        new_id = connection.execute(
            insert(LlmUsageRow).values(**_usage(user_id, "chat")).returning(LlmUsageRow.id)
        ).scalar_one()

    assert new_id > _count(source, "llm_usage")


def test_orphan_rows_and_overlong_text_are_reported_and_block_the_copy(tmp_path: Path) -> None:
    url, source = _filled_source(tmp_path)
    raw = sqlite3.connect(url.removeprefix("sqlite:///"))  # foreign keys off, as v3 ran
    raw.execute("UPDATE users SET name = ?", ("x" * 61,))
    raw.execute(
        "INSERT INTO engine_results (game_id, fen, position_key, tier, depth, time_ms, lines, "
        "created_at) VALUES ('gone', 'f', 'f', 'scan', 1, 1, '[]', '2026-11-23 12:00:00')"
    )
    raw.commit()
    raw.close()

    problems = find_problems(source)

    kinds = {(p.kind, p.table, p.column) for p in problems}
    assert ("missing_parent", "engine_results", "game_id") in kinds
    assert ("too_long", "users", "name") in kinds
    with pytest.raises(CopyError, match="problems"):
        copy_database(source, _empty_target())


def test_a_target_with_data_is_refused(tmp_path: Path) -> None:
    _, source = _filled_source(tmp_path)
    target = _empty_target()
    copy_database(source, target)

    with pytest.raises(CopyError, match="not empty"):
        copy_database(source, target)


def test_a_source_behind_the_latest_schema_is_refused(tmp_path: Path) -> None:
    source = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    upgrade(source)
    with source.begin() as connection:
        connection.exec_driver_sql("UPDATE alembic_version SET version_num = '0017'")

    with pytest.raises(CopyError, match="latest schema"):
        copy_database(source, _empty_target())


def test_the_cli_checks_without_writing_then_copies(tmp_path: Path) -> None:
    url, _ = _filled_source(tmp_path)
    # The CLI opens its own engines, so on SQLite the target must be a file.
    target_url = (
        fresh_database_url(migrated=False) if is_postgres() else f"sqlite:///{tmp_path / 'pg.db'}"
    )
    settings = Settings(_env_file=None, database_url=url)
    command = ["migrate-sqlite", "--from", url, "--to", target_url]

    check_out = io.StringIO()
    assert main([*command, "--check-only"], settings, check_out) == 0
    assert "No problems found" in check_out.getvalue()
    assert "users" not in inspect(make_engine(target_url)).get_table_names()

    copy_out = io.StringIO()
    assert main(command, settings, copy_out) == 0
    assert "every table matches" in copy_out.getvalue()
    assert _count(make_engine(target_url), "users") == 1


def test_check_only_needs_no_target_and_a_copy_does(tmp_path: Path) -> None:
    url, _ = _filled_source(tmp_path)
    settings = Settings(_env_file=None, database_url=url)

    assert main(["migrate-sqlite", "--from", url, "--check-only"], settings, io.StringIO()) == 0
    assert main(["migrate-sqlite", "--from", url], settings, io.StringIO()) == 1


def test_a_source_that_isnt_a_sqlite_file_is_refused(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, database_url="sqlite://")
    command = ["migrate-sqlite", "--from", "postgresql+psycopg://x/y", "--check-only"]

    assert main(command, settings, io.StringIO()) == 1
