"""What every game importer shares (SPEC_V3 §10): the query, the games it returns, and the ways
a platform can fail. Importers only fetch PGNs; parsing and checks happen as for any upload."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from app.api.schemas import Platform, TimeControl
from app.config import ImportSettings

FailureKind = Literal["not_found", "rate_limited", "unavailable"]

PLATFORM_NAME: dict[Platform, str] = {"lichess": "Lichess", "chesscom": "Chess.com"}


class ImportedGame(BaseModel):
    model_config = ConfigDict(frozen=True)

    platform: Platform
    external_id: str
    pgn: str
    url: str | None
    played_at: datetime | None


@dataclass(frozen=True)
class ImportQuery:
    username: str
    max_games: int
    category: TimeControl | None = None
    since: date | None = None


class ImportFailure(Exception):
    """The platform couldn't give the games: no such player, too many requests, or down."""

    def __init__(self, kind: FailureKind, platform: Platform, username: str) -> None:
        self.kind = kind
        self.platform = platform
        self.username = username
        super().__init__(failure_message(kind, platform, username))


def failure_message(kind: FailureKind, platform: Platform, username: str) -> str:
    name = PLATFORM_NAME[platform]
    if kind == "not_found":
        return f"{name} has no player called {username}. Check the username on your profile."
    if kind == "rate_limited":
        return f"{name} asked us to slow down. Please try again in a minute."
    return f"{name} isn't answering right now. Please try again later."


def failure_for(response: httpx.Response, platform: Platform, username: str) -> ImportFailure:
    """The failure an error response stands for."""
    if response.status_code in (404, 410):
        return ImportFailure("not_found", platform, username)
    if response.status_code == 429:
        return ImportFailure("rate_limited", platform, username)
    return ImportFailure("unavailable", platform, username)


def headers(settings: ImportSettings, accept: str) -> dict[str, str]:
    return {"User-Agent": settings.user_agent(), "Accept": accept}
