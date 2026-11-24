from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from tests.auth_helpers import BASE_URL, log_in
from tests.databases import drop_test_databases, fresh_database_url


@pytest.fixture(autouse=True)
def _drop_test_databases() -> Iterator[None]:
    """On Postgres, drop each test's databases when it ends (no-op on SQLite)."""
    yield
    drop_test_databases()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, database_url=fresh_database_url())


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Logged in as "Owner" (Elo 1350, rapid). Most tests act as one player."""
    return log_in(app, "Owner")


@pytest.fixture
def anon_client(app: FastAPI) -> TestClient:
    """No session cookie."""
    return TestClient(app, base_url=BASE_URL)


@pytest.fixture
def db_session(app: FastAPI) -> Iterator[Session]:
    with app.state.session_factory() as session:
        yield session
