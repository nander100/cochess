from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "database": "ok", "migrations": "ok"}


def test_health_fails_when_migrations_are_behind(app: FastAPI, client: TestClient) -> None:
    with app.state.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '0001'"))

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"ok": False, "database": "ok", "migrations": "behind"}


def test_health_fails_when_the_database_is_unreachable(app: FastAPI, client: TestClient) -> None:
    app.state.engine = create_engine("postgresql+psycopg://nobody@127.0.0.1:1/none")

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"


def test_responses_carry_cross_origin_isolation_headers(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Embedder-Policy"] == "require-corp"
