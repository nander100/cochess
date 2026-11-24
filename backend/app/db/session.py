"""Database engine construction."""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.pool import StaticPool

_IN_MEMORY_URLS = frozenset({"sqlite://", "sqlite:///:memory:"})


def make_engine(database_url: str) -> Engine:
    if not database_url.startswith("sqlite"):
        # Postgres (SPEC_V4 §12.1): RDS closes idle connections, so check each one before use.
        return create_engine(database_url, pool_pre_ping=True)
    # FastAPI runs sync endpoints in a threadpool, so SQLite connections cross threads.
    connect_args = {"check_same_thread": False}
    if database_url in _IN_MEMORY_URLS:
        # One shared connection, or each connection would get its own empty database.
        engine = create_engine(database_url, connect_args=connect_args, poolclass=StaticPool)
    else:
        engine = create_engine(database_url, connect_args=connect_args)
    event.listen(engine, "connect", _enforce_foreign_keys)
    return engine


def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    """SQLite ignores foreign keys unless asked, and Postgres doesn't (PLAN_V4 adjustment 5)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
