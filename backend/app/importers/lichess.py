"""Recent games from Lichess's public API (GET /api/games/user/{username}, NDJSON)."""

import json
from datetime import UTC, datetime, time

import httpx

from app.config import ImportSettings
from app.importers.base import ImportedGame, ImportFailure, ImportQuery, failure_for, headers

PERF_TYPE = {"bullet": "bullet", "blitz": "blitz", "rapid": "rapid", "classical": "classical"}


def fetch_lichess(
    client: httpx.Client, query: ImportQuery, settings: ImportSettings
) -> list[ImportedGame]:
    """The player's latest standard games, newest first."""
    params: dict[str, str | int] = {"max": query.max_games, "pgnInJson": "true", "clocks": "true"}
    if query.category is not None:
        params["perfType"] = PERF_TYPE[query.category]
    if query.since is not None:
        start = datetime.combine(query.since, time.min, tzinfo=UTC)
        params["since"] = int(start.timestamp() * 1000)
    url = f"{settings.lichess_url}/api/games/user/{query.username}"
    try:
        response = client.get(url, params=params, headers=headers(settings, "application/x-ndjson"))
    except httpx.HTTPError as error:
        raise ImportFailure("unavailable", "lichess", query.username) from error
    if response.status_code != 200:
        raise failure_for(response, "lichess", query.username)
    return [game for line in response.text.splitlines() if (game := _game(line, settings))]


def _game(line: str, settings: ImportSettings) -> ImportedGame | None:
    if not line.strip():
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    game_id, pgn = data.get("id"), data.get("pgn")
    if data.get("variant", "standard") != "standard" or not isinstance(game_id, str) or not pgn:
        return None  # Chess960, From Position and the like aren't analyzed
    created = data.get("lastMoveAt") or data.get("createdAt")
    played_at = datetime.fromtimestamp(created / 1000, tz=UTC) if isinstance(created, int) else None
    return ImportedGame(
        platform="lichess",
        external_id=game_id,
        pgn=str(pgn),
        url=f"{settings.lichess_url}/{game_id}",
        played_at=played_at,
    )
