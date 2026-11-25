"""Every API route needs a login, and no one can reach another player's game (SPEC_V2 §4.2).

The routes come from the app's own route table, so a new route is covered automatically: it
fails here unless it requires a session and scopes `{game_id}` to the current user.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import BASE_URL, log_in
from tests.coach_fakes import FakeCoachClient
from tests.databases import fresh_database_url

PUBLIC = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/redeem"),
    ("POST", "/api/auth/logout"),
    # Signing in with Google (SPEC_V4 §4) starts logged out; the sign-up form is tied to its own
    # short-lived cookie instead (tests/auth/test_google_routes.py).
    ("GET", "/api/auth/google/start"),
    ("GET", "/api/auth/google/callback"),
    ("GET", "/api/auth/signup"),
    ("POST", "/api/auth/signup"),
    # The payment provider's webhook: its signature is the check (tests/billing).
    ("POST", "/api/billing/webhook"),
    # The terms and privacy texts (SPEC_V4 §11) are read before anyone signs up.
    ("GET", "/api/legal/{kind}"),
}


def _app() -> FastAPI:
    # A coach client is configured, so coach routes can't answer 503 before checking ownership.
    return create_app(
        Settings(_env_file=None, database_url=fresh_database_url()), FakeCoachClient([])
    )


# From the OpenAPI schema: FastAPI 0.16x nests included routers, so `app.routes` doesn't list
# their routes, while the schema lists every route of the app.
ROUTES = sorted(
    (method.upper(), path)
    for path, operations in _app().openapi()["paths"].items()
    if path.startswith("/api/")
    for method in operations
)
# The owner dashboard (SPEC_V4 §10) answers 404 to everyone but an owner, signed in or not, so
# it doesn't show it exists (tests/admin/test_admin_api.py checks players get 404 too).
ADMIN = [route for route in ROUTES if route[1].startswith("/api/admin/")]
PRIVATE = [route for route in ROUTES if route not in PUBLIC and route not in ADMIN]
GAME_ROUTES = [route for route in PRIVATE if "{game_id}" in route[1]]


def _request(client: TestClient, method: str, path: str, game_id: str) -> int:
    url = path.replace("{game_id}", game_id)
    body = None if method == "GET" else {}
    return client.request(method, url, json=body).status_code


@pytest.fixture
def setup() -> tuple[FastAPI, TestClient, TestClient, str]:
    app = _app()
    owner, other = log_in(app, "Owner"), log_in(app, "Other")
    return app, owner, other, analyzed_game(owner, "white")


def test_the_route_table_has_the_routes_we_expect() -> None:
    assert len(GAME_ROUTES) >= 5  # scan, verify, synopsis, chat, chat/engine_result
    assert ("GET", "/api/me") in PRIVATE


@pytest.mark.parametrize(("method", "path"), PRIVATE)
def test_every_private_route_needs_a_login(
    setup: tuple[FastAPI, TestClient, TestClient, str], method: str, path: str
) -> None:
    app, _, _, game_id = setup

    assert _request(TestClient(app, base_url=BASE_URL), method, path, game_id) == 401


@pytest.mark.parametrize(("method", "path"), GAME_ROUTES)
def test_another_players_game_is_not_found(
    setup: tuple[FastAPI, TestClient, TestClient, str], method: str, path: str
) -> None:
    _, owner, other, game_id = setup

    assert _request(other, method, path, game_id) == 404
    assert _request(owner, method, path, game_id) != 404  # the owner gets past the check


@pytest.mark.parametrize(("method", "path"), ADMIN)
def test_owner_routes_are_not_found_without_a_login(
    setup: tuple[FastAPI, TestClient, TestClient, str], method: str, path: str
) -> None:
    app, _, _, game_id = setup
    url = path.replace("{user_id}", "someone")

    assert _request(TestClient(app, base_url=BASE_URL), method, url, game_id) == 404


def test_the_owner_routes_are_all_found() -> None:
    assert len(ADMIN) >= 9  # overview, users, a user, bulk accept and five actions
