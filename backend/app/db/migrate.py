"""Bring a database to the latest schema with Alembic (SPEC_V2 §4.4).

A database created by v1 (`create_all`, no `alembic_version` table) is stamped at the v1
baseline first, so only the v2 migrations run on it.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect

BASELINE = "0001"
_BACKEND = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    return config


def upgrade(engine: Engine) -> None:
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "games" in tables and "alembic_version" not in tables:
            command.stamp(config, BASELINE)
        command.upgrade(config, "head")
