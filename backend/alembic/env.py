"""Alembic environment. Uses the caller's connection when one is passed in `config.attributes`
(the app at startup, and tests), otherwise connects to the configured DATABASE_URL (the CLI)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.config import get_settings
from app.db.models import Base
from app.db.session import make_engine

config = context.config
target_metadata = Base.metadata


def run(connection: Connection) -> None:
    # SQLite can't ALTER most things; batch mode rebuilds tables instead (move and copy).
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


shared = config.attributes.get("connection")
if shared is not None:
    run(shared)
else:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    engine = make_engine(get_settings().database_url)
    with engine.connect() as connection:
        run(connection)
