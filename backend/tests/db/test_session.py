"""Database engines (SPEC_V4 §12.1, PLAN_V4 adjustment 5): SQLite enforces foreign keys like
Postgres does, and Postgres connections are checked before use."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import upgrade
from app.db.session import make_engine
from tests.databases import fresh_database_url, is_postgres

_GAME_WITH_UNKNOWN_USER = text(
    "INSERT INTO games (id, user_id, pgn, user_color, elo, headers, created_at) "
    "VALUES ('g1', 'no-such-user', '1. e4 *', 'white', 1400, '{}', '2026-11-23 12:00:00')"
)


def test_a_row_pointing_at_a_missing_user_is_rejected() -> None:
    engine = make_engine(fresh_database_url(migrated=False))
    upgrade(engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(_GAME_WITH_UNKNOWN_USER)


def test_sqlite_file_databases_enforce_foreign_keys_too(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'fk.db'}")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_sqlite_file_databases_use_wal_and_wait_for_locks(tmp_path: Path) -> None:
    """Litestream backs SQLite up from its write-ahead log, and needs the app to wait briefly
    rather than fail when it checkpoints (docs/DEPLOY.md, "Backups")."""
    engine = make_engine(f"sqlite:///{tmp_path / 'wal.db'}")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_an_in_memory_database_keeps_its_own_journal() -> None:
    engine = make_engine("sqlite://")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "memory"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000


@pytest.mark.skipif(not is_postgres(), reason="needs TEST_DATABASE_URL (Postgres)")
def test_postgres_connections_are_checked_before_use() -> None:
    engine = make_engine(fresh_database_url())

    assert engine.pool._pre_ping is True
