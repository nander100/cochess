"""Test databases (SPEC_V4 §12.1): in-memory SQLite, or Postgres when TEST_DATABASE_URL is set.

On Postgres every test gets its own database, cloned from a template migrated once per run, and
dropped after the test (`drop_test_databases`, called from conftest), so tests stay isolated and
idle connections from each test's app don't pile up.
"""

import os
import uuid

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.db.migrate import upgrade
from app.db.session import make_engine

ADMIN_URL = os.environ.get("TEST_DATABASE_URL", "")
SQLITE_MEMORY = "sqlite://"
_TEMPLATE = "cochess_test_template"
_PREFIX = "cochess_test_"

_created: list[str] = []
_template_ready = False


def is_postgres() -> bool:
    return ADMIN_URL.startswith("postgresql")


def fresh_database_url(*, migrated: bool = True) -> str:
    """A new, empty database for one test: at the latest schema, or with no tables at all.

    On SQLite it's an in-memory database, which the app migrates at startup as before.
    """
    if not is_postgres():
        return SQLITE_MEMORY
    template = _migrated_template() if migrated else "template0"
    name = f"{_PREFIX}{uuid.uuid4().hex[:12]}"
    with _admin().connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{template}"'))
    _created.append(name)
    return _url_for(name)


def drop_test_databases() -> None:
    """Drop the databases made since the last call. FORCE ends the test apps' open connections."""
    if not _created:
        return
    with _admin().connect() as connection:
        while _created:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{_created.pop()}" WITH (FORCE)'))


def _migrated_template() -> str:
    global _template_ready
    if not _template_ready:
        with _admin().connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{_TEMPLATE}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{_TEMPLATE}" TEMPLATE template0'))
        engine = make_engine(_url_for(_TEMPLATE))
        upgrade(engine)
        engine.dispose()  # a template can't be cloned while anyone is connected to it
        _template_ready = True
    return _TEMPLATE


def _admin() -> Engine:
    return create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)


def _url_for(name: str) -> str:
    return make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
