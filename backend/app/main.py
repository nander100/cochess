"""FastAPI application factory and middleware. Run with `uvicorn app.main:create_app --factory`."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from sqlalchemy.orm import sessionmaker

from app.api import coach as coach_routes
from app.api import engine as engine_routes
from app.api import games
from app.coach.client import AnthropicCoachClient, CoachClient
from app.config import Settings, get_settings
from app.db.models import Base
from app.db.session import make_engine

# Required for SharedArrayBuffer, which multi-threaded Stockfish WASM needs (SPEC §4.1).
CROSS_ORIGIN_ISOLATION_HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
}


def create_app(
    settings: Settings | None = None, coach_client: CoachClient | None = None
) -> FastAPI:
    """`coach_client` is injected by tests; otherwise it's built from ANTHROPIC_API_KEY (and is
    None without a key, so coach endpoints answer 503 instead of failing at startup)."""
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    # v1 has no migrations (PLAN Q12); Alembic arrives with Postgres in v2.
    Base.metadata.create_all(engine)

    app = FastAPI(title="CoChess")
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    if coach_client is None and settings.anthropic_api_key:
        coach_client = AnthropicCoachClient(settings.anthropic_api_key)
    app.state.coach_client = coach_client

    @app.middleware("http")
    async def cross_origin_isolation(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.update(CROSS_ORIGIN_ISOLATION_HEADERS)
        return response

    @app.get("/api/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(games.router)
    app.include_router(engine_routes.router)
    app.include_router(coach_routes.router)
    return app
