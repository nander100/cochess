from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.auth.service import create_invite, create_user
from app.config import Settings

COOKIE = "cochess_session"


@pytest.fixture
def secure_client(app: FastAPI) -> TestClient:
    """HTTPS, so the Secure session cookie is sent back like a browser would."""

    @app.get("/api/test/whoami")
    def whoami(user: CurrentUser) -> dict[str, str]:
        return {"name": user.name}

    return TestClient(app, base_url="https://testserver")


def _invite(db_session: Session, settings: Settings, name: str = "Alex") -> str:
    user = create_user(db_session, name)
    return create_invite(db_session, user, datetime.now(UTC), settings.auth)


def test_redeem_sets_an_httponly_secure_lax_session_cookie(
    secure_client: TestClient, db_session: Session, settings: Settings
) -> None:
    response = secure_client.post("/api/auth/redeem", json={"token": _invite(db_session, settings)})

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=2592000" in cookie  # 30 days
    assert secure_client.get("/api/test/whoami").json() == {"name": "Alex"}


def test_redeeming_a_used_link_fails_with_a_clear_message(
    secure_client: TestClient, db_session: Session, settings: Settings
) -> None:
    token = _invite(db_session, settings)
    secure_client.post("/api/auth/redeem", json={"token": token})

    response = TestClient(secure_client.app).post("/api/auth/redeem", json={"token": token})

    assert response.status_code == 400
    assert "expired or was already used" in response.json()["detail"]


def test_requests_without_a_session_get_401(secure_client: TestClient) -> None:
    response = secure_client.get("/api/test/whoami")

    assert response.status_code == 401
    assert "not logged in" in response.json()["detail"]


def test_a_made_up_session_cookie_gets_401(secure_client: TestClient) -> None:
    secure_client.cookies.set(COOKIE, "forged")

    assert secure_client.get("/api/test/whoami").status_code == 401


def test_logout_ends_the_session_and_clears_the_cookie(
    secure_client: TestClient, db_session: Session, settings: Settings
) -> None:
    secure_client.post("/api/auth/redeem", json={"token": _invite(db_session, settings)})
    stolen = secure_client.cookies[COOKIE]

    response = secure_client.post("/api/auth/logout")

    assert response.status_code == 204
    assert f'{COOKIE}=""' in response.headers["set-cookie"]
    assert secure_client.get("/api/test/whoami").status_code == 401
    secure_client.cookies.set(COOKIE, stolen)  # the old token no longer works either
    assert secure_client.get("/api/test/whoami").status_code == 401


def test_logout_without_a_session_is_harmless(secure_client: TestClient) -> None:
    assert secure_client.post("/api/auth/logout").status_code == 204
