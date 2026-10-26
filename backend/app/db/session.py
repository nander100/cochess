"""Database engine construction."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

_IN_MEMORY_URLS = frozenset({"sqlite://", "sqlite:///:memory:"})


def make_engine(database_url: str) -> Engine:
    if not database_url.startswith("sqlite"):
        return create_engine(database_url)
    # FastAPI runs sync endpoints in a threadpool, so SQLite connections cross threads.
    connect_args = {"check_same_thread": False}
    if database_url in _IN_MEMORY_URLS:
        # One shared connection, or each connection would get its own empty database.
        return create_engine(database_url, connect_args=connect_args, poolclass=StaticPool)
    return create_engine(database_url, connect_args=connect_args)
