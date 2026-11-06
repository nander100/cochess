"""One entry point for both platforms."""

import httpx

from app.api.schemas import Platform
from app.config import ImportSettings
from app.importers.base import ImportedGame, ImportQuery
from app.importers.chesscom import fetch_chesscom
from app.importers.lichess import fetch_lichess


def fetch_games(
    platform: Platform,
    query: ImportQuery,
    settings: ImportSettings,
    transport: httpx.BaseTransport | None = None,
) -> list[ImportedGame]:
    """The player's recent games from one platform. `transport` lets tests fake the platform."""
    with httpx.Client(
        transport=transport, timeout=settings.timeout_seconds, follow_redirects=True
    ) as client:
        if platform == "lichess":
            return fetch_lichess(client, query, settings)
        return fetch_chesscom(client, query, settings)
