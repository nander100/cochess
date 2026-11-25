"""FastAPI application factory and middleware. Run with `uvicorn app.main:create_app --factory`."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from sqlalchemy.orm import sessionmaker

from app.admin import routes as admin_routes
from app.api import billing_routes, games, profile, settings_routes, validation
from app.api import coach as coach_routes
from app.api import credits as credit_routes
from app.api import dashboard as dashboard_routes
from app.api import engine as engine_routes
from app.api import imports as import_routes
from app.api import lines as line_routes
from app.api import moments as moment_routes
from app.api import onboarding as onboarding_routes
from app.api import onboarding_import as onboarding_import_routes
from app.api import tendencies as tendency_routes
from app.api import variations as variation_routes
from app.api import walkthrough as walkthrough_routes
from app.auth import google_routes
from app.auth import routes as auth_routes
from app.billing.stripe_provider import StripeProvider
from app.coach.client import AnthropicCoachClient, CoachClient
from app.config import Settings, get_settings
from app.db.migrate import upgrade
from app.db.session import make_engine
from app.email.smtp import EmailSender, SmtpTransport

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
    upgrade(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Account email (SPEC_V4 §12.4) is sent from a background thread, only when it's on;
        # otherwise queued emails are marked skipped by whoever runs send_pending.
        if settings.email.enabled:
            transport = app.state.email_transport or SmtpTransport(settings.email)
            app.state.email_sender = EmailSender(app.state.session_factory, settings, transport)
            app.state.email_sender.start()
        try:
            yield
        finally:
            if app.state.email_sender is not None:
                app.state.email_sender.stop()

    app = FastAPI(title="CoChess", lifespan=lifespan)
    app.state.email_transport = None  # tests put a recording transport here
    app.state.email_sender = None
    validation.install(app)
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    if coach_client is None and settings.anthropic_api_key:
        coach_client = AnthropicCoachClient(settings.anthropic_api_key)
    app.state.coach_client = coach_client
    # Payments (SPEC_V4 §6): off without a Stripe key (checkout answers 503); tests put a fake here.
    app.state.billing_provider = (
        StripeProvider(settings.stripe) if settings.stripe.enabled else None
    )

    # Every API route except health, redeem and the Google sign-in routes requires a login
    # session (app/auth), checked per route: CurrentUser for active players, CurrentAccount for
    # the status page a waitlisted or paused player sees (SPEC_V4 §4).
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

    app.include_router(auth_routes.router)
    app.include_router(google_routes.router)
    app.include_router(profile.router)
    app.include_router(games.router)
    app.include_router(engine_routes.router)
    app.include_router(coach_routes.router)
    app.include_router(moment_routes.router)
    app.include_router(tendency_routes.router)
    app.include_router(onboarding_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(variation_routes.router)
    app.include_router(walkthrough_routes.router)
    app.include_router(line_routes.router)
    app.include_router(dashboard_routes.router)
    app.include_router(import_routes.router)
    app.include_router(onboarding_import_routes.router)
    app.include_router(credit_routes.router)
    app.include_router(billing_routes.router)
    app.include_router(admin_routes.router)
    return app
