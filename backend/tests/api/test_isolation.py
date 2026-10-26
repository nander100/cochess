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

PUBLIC = {("GET", "/api/health"), ("POST", "/api/auth/redeem"), ("POST", "/api/auth/logout")}


def _app() -> FastAPI:
    # A coach client is configured, so coach routes can't answer 503 before checking ownership.
    return create_app(Settings(_env_file=None, database_url="sqlite://"), FakeCoachClient([]))


# From the OpenAPI schema: FastAPI 0.16x nests included routers, so `app.routes` doesn't list
# their routes, while the schema lists every route of the app.
ROUTES = sorted(
    (method.upper(), path)
    for path, operations in _app().openapi()["paths"].items()
    if path.startswith("/api/")
    for method in operations
)
PRIVATE = [route for route in ROUTES if route not in PUBLIC]
GAME_ROUTES = [route for route in PRIVATE if "{game_id}" in route[1]]


def _request(client: TestClient, method: str, path: str, game_id: str) -> int:
    url = path.replace("{game_id}", game_id)
    body = None if method == "GET" else {}
    return client.request(method, url, json=body).status_code


@pytest.fixture
def setup() -> tuple[FastAPI, TestClient, TestClient, str]:
    app = _app()
    owner, other = log_in(app, "Owner"), log_in(app, "Other")
    return app, owner, other, analyzed_game(owner)


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
