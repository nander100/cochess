"""FastAPI application factory and middleware."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

# Required for SharedArrayBuffer, which multi-threaded Stockfish WASM needs (SPEC §4.1).
CROSS_ORIGIN_ISOLATION_HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
}


def create_app() -> FastAPI:
    app = FastAPI(title="CoChess")

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

    return app


app = create_app()
