"""Bring a database to the latest schema with Alembic (SPEC_V2 §4.4).

A database created by v1 (`create_all`, no `alembic_version` table) is stamped at the v1
baseline first, so only the v2 migrations run on it.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect

BASELINE = "0001"
_BACKEND = Path(__file__).resolve().parents[2]


class ForeignKeyError(RuntimeError):
    """The migrated SQLite database has rows that point at rows that don't exist."""


def alembic_config() -> Config:
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    return config


def upgrade(engine: Engine) -> None:
    config = alembic_config()
    with engine.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # Batch migrations rebuild SQLite tables (copy, drop, rename), which foreign-key
            # checks would break halfway. Switched off outside the transaction (SQLite ignores
            # the pragma inside one), checked once the migrations are done.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()  # end the transaction SQLAlchemy opened for the pragma
        try:
            with connection.begin():
                _run(config, connection)
            if sqlite:
                _check_foreign_keys(connection)
        finally:
            if sqlite:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()


def _run(config: Config, connection: Connection) -> None:
    config.attributes["connection"] = connection
    tables = set(inspect(connection).get_table_names())
    if "games" in tables and "alembic_version" not in tables:
        command.stamp(config, BASELINE)
    command.upgrade(config, "head")


def _check_foreign_keys(connection: Connection) -> None:
    problems = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    connection.commit()  # end the transaction SQLAlchemy opened for the pragma
    if problems:
        tables = sorted({str(row[0]) for row in problems})
        raise ForeignKeyError(
            f"{len(problems)} rows point at missing rows (tables: {', '.join(tables)}). "
            "Run `python -m app.cli migrate-sqlite --check-only` to list them."
        )
