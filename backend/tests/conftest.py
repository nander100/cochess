from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from tests.auth_helpers import BASE_URL, log_in


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, database_url="sqlite://")


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
