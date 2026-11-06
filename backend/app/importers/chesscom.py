"""Recent games from Chess.com's public API: the player's monthly archives, newest first."""

from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import ImportSettings
from app.importers.base import ImportedGame, ImportFailure, ImportQuery, failure_for, headers


def fetch_chesscom(
    client: httpx.Client, query: ImportQuery, settings: ImportSettings
) -> list[ImportedGame]:
    """The player's latest standard games, newest first. Archives are read one at a time, as
    Chess.com asks of API clients (no parallel requests)."""
    base = f"{settings.chesscom_url}/pub/player/{query.username.lower()}"
    archives = _json(client, f"{base}/games/archives", query, settings).get("archives", [])
    games: list[ImportedGame] = []
    for url in list(reversed(archives))[: settings.chesscom_max_archives]:
        # Only follow archive links on the API itself.
        if not isinstance(url, str) or not url.startswith(f"{base}/games/"):
            continue
        if query.since is not None and _month_end(url) < query.since.year * 12 + query.since.month:
            break
        for data in reversed(_json(client, url, query, settings).get("games", [])):
            game = _game(data, query)
            if game is not None:
                games.append(game)
            if len(games) >= query.max_games:
                return games
    return games


def _json(
    client: httpx.Client, url: str, query: ImportQuery, settings: ImportSettings
) -> dict[str, Any]:
    try:
        response = client.get(url, headers=headers(settings, "application/json"))
    except httpx.HTTPError as error:
        raise ImportFailure("unavailable", "chesscom", query.username) from error
    if response.status_code != 200:
        raise failure_for(response, "chesscom", query.username)
    try:
        body = response.json()
    except ValueError as error:
        raise ImportFailure("unavailable", "chesscom", query.username) from error
    return body if isinstance(body, dict) else {}


def _month_end(url: str) -> int:
    """An archive URL's month as year * 12 + month (…/games/2026/10)."""
    try:
        year, month = url.rstrip("/").split("/")[-2:]
        return int(year) * 12 + int(month)
    except ValueError:
        return 0


def _game(data: Any, query: ImportQuery) -> ImportedGame | None:
    if not isinstance(data, dict) or data.get("rules") != "chess":
        return None  # Chess960, bughouse and other variants aren't analyzed
    url, pgn, end = data.get("url"), data.get("pgn"), data.get("end_time")
    if not isinstance(url, str) or not isinstance(pgn, str) or not pgn:
        return None
    if query.category is not None and data.get("time_class") != query.category:
        return None
    played_at = datetime.fromtimestamp(end, tz=UTC) if isinstance(end, int) else None
    if query.since is not None and played_at is not None and played_at.date() < query.since:
        return None
    return ImportedGame(
        platform="chesscom",
        external_id=url.rstrip("/").rsplit("/", 1)[-1],
        pgn=pgn,
        url=url,
        played_at=played_at,
    )
