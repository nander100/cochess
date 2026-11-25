"""Owner-dashboard test helpers: an owner's client, players in each state, and rows of usage and
payments written straight to the database (no coach or Stripe calls)."""

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import create_user
from app.config import Settings
from app.db.models import BillingEventRow, LlmUsageRow, User
from app.main import create_app
from tests.auth_helpers import log_in
from tests.coach_fakes import FakeCoachClient
from tests.databases import fresh_database_url

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
CREDIT = 10_000


def admin_app(**settings: Any) -> FastAPI:
    return create_app(
        Settings(_env_file=None, database_url=fresh_database_url(), **settings), FakeCoachClient([])
    )


def owner_client(app: FastAPI, name: str = "Owner") -> TestClient:
    client = log_in(app, name)
    with app.state.session_factory() as session:
        user = by_name(session, name)
        user.role = "owner"
        session.commit()
    return client


def by_name(session: Session, name: str) -> User:
    return session.scalars(select(User).where(User.name == name)).one()


def player(
    app: FastAPI,
    name: str,
    *,
    status: str = "active",
    email: str | None = None,
    waitlisted_at: datetime | None = None,
    created_at: datetime | None = None,
) -> str:
    with app.state.session_factory() as session:
        user = create_user(session, name)
        user.status, user.email = status, email
        user.waitlisted_at = waitlisted_at if status == "waitlisted" else None
        user.admitted_at = NOW if status != "waitlisted" else None
        if created_at is not None:
            user.created_at = created_at
        session.commit()
        return user.id


def usage(
    session: Session,
    user_id: str | None,
    cost: int,
    at: datetime,
    *,
    task: str = "chat",
    tokens: tuple[int, int, int] = (100, 0, 0),
) -> None:
    fresh, read, written = tokens
    session.add(
        LlmUsageRow(
            user_id=user_id,
            endpoint=task,
            task=task,
            model="fake-model",
            input_tokens=fresh,
            output_tokens=10,
            cache_read_tokens=read,
            cache_write_tokens=written,
            cost_microusd=cost,
            created_at=at,
        )
    )


def billing_event(
    session: Session,
    event_id: str,
    kind: str,
    cents: int | None,
    at: datetime,
    *,
    outcome: str = "applied",
    user_id: str | None = None,
    object_id: str | None = None,
) -> None:
    session.add(
        BillingEventRow(
            provider="stripe",
            event_id=event_id,
            type=kind,
            user_id=user_id,
            amount_cents=cents,
            currency="usd",
            object_id=object_id,
            outcome=outcome,
            received_at=at,
        )
    )
