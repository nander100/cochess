"""Request-scoped dependencies. The app's settings and session factory live on `app.state`."""

from collections.abc import Iterator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_session(request: Request) -> Iterator[Session]:
    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    with factory() as session:
        yield session
