"""Logged-in test clients: a real invite redeemed for a real session cookie."""

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.service import create_invite, create_user
from app.config import Settings

# HTTPS, so the Secure session cookie is sent back like a browser would.
BASE_URL = "https://testserver"


def log_in(
    app: FastAPI,
    name: str,
    *,
    elo: int | None = 1350,
    time_control: str | None = "rapid",
    playstyle: str | None = None,
) -> TestClient:
    """A client logged in as a new user `name` with the given profile."""
    settings: Settings = app.state.settings
    with app.state.session_factory() as session:
        user = create_user(session, name)
        user.elo, user.time_control, user.playstyle = elo, time_control, playstyle
        session.commit()
        token = create_invite(session, user, datetime.now(UTC), settings.auth)
    client = TestClient(app, base_url=BASE_URL)
    response = client.post("/api/auth/redeem", json={"token": token})
    assert response.status_code == 204, response.text
    return client
