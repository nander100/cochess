"""POST /api/import (SPEC_V3 §10): the player's recent games from Lichess or Chess.com, as a
review table. Nothing is stored here: games are added through the usual upload or assessment
routes, which parse and check them again."""

import math
from datetime import UTC, date, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.evals import Color
from app.analysis.onboarding import detect_color, time_control_category
from app.analysis.pgn import PgnError, parse_pgn
from app.api.deps import get_app_settings, get_session
from app.api.games import games_left_today
from app.api.schemas import PgnErrorDetail, Platform, TimeControl
from app.auth.deps import CurrentUser
from app.config import Settings
from app.db.games import find_duplicate, find_external, game_fingerprint
from app.db.models import Game, UserSettingsRow
from app.db.user_settings import usernames_for
from app.importers.base import PLATFORM_NAME, ImportedGame, ImportFailure, ImportQuery
from app.importers.service import fetch_games
from app.limits import check

router = APIRouter(prefix="/api/import", tags=["import"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

FAILURE_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    "unavailable": status.HTTP_502_BAD_GATEWAY,
}


class ImportRequest(BaseModel):
    platform: Platform
    max: int | None = Field(default=None, ge=1)  # default and cap from config
    tc: TimeControl | None = None
    since: date | None = None


class ImportRow(BaseModel):
    index: int
    platform: Platform
    external_id: str
    url: str | None
    pgn: str | None  # the cleaned PGN to add; None when it can't be analyzed
    white: str | None
    black: str | None
    result: str | None
    date: str | None
    time_control: str | None
    category: TimeControl | None
    # The side the player's own username played (owner decision, 2026-11-06), else None.
    user_color: Color | None
    already_imported: bool
    error: PgnErrorDetail | None


class ImportResponse(BaseModel):
    platform: Platform
    username: str
    games: list[ImportRow]
    # Imported games count toward the daily cap (owner decision 2026-11-06).
    games_left_today: int


@router.post("")
def import_games(
    body: ImportRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> ImportResponse:
    limit = min(body.max or settings.imports.default_games, settings.imports.max_games)
    username, fetched = fetch_recent(
        request, session, user.id, settings, body.platform, limit, body.tc, body.since
    )
    known_ids, known_prints = _known(session, user.id, body.platform)
    usernames = usernames_for(session, user.id)
    rows = [
        _row(i, game, settings, usernames, known_ids, known_prints)
        for i, game in enumerate(fetched)
    ]
    return ImportResponse(
        platform=body.platform,
        username=username,
        games=rows,
        games_left_today=games_left_today(session, user.id, settings),
    )


class LatestGame(BaseModel):
    """The player's newest game across their linked platforms (owner request 2026-11-06)."""

    game: ImportRow
    # Set when the player already has this game: the page opens it instead of adding it again.
    existing_game_id: str | None


@router.post("/latest")
def latest_game(
    request: Request, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> LatestGame:
    """One click from the home page: the newest game the player finished on Chess.com or
    Lichess (whichever is newer when both are linked), ready to add and analyze."""
    linked = _linked(session, user.id)
    if not linked:
        detail = "Add your Chess.com or Lichess username on your profile first."
        raise HTTPException(status.HTTP_409_CONFLICT, detail=detail)
    _cool_down(session, user.id, settings)
    transport = getattr(request.app.state, "import_transport", None)
    found: list[ImportedGame] = []
    failures: list[ImportFailure] = []
    for platform, username in linked:
        try:
            found += fetch_games(platform, ImportQuery(username, 1), settings.imports, transport)
        except ImportFailure as failure:
            failures.append(failure)  # the other platform may still have the game
    if not found:
        if failures:
            first = failures[0]
            raise HTTPException(FAILURE_STATUS[first.kind], detail=str(first))
        names = " or ".join(f"{PLATFORM_NAME[p]} ({u})" for p, u in linked)
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"No games found on {names}.")
    newest = max(found, key=lambda game: game.played_at or datetime.min.replace(tzinfo=UTC))
    known_ids, known_prints = _known(session, user.id, newest.platform)
    row = _row(0, newest, settings, usernames_for(session, user.id), known_ids, known_prints)
    existing = _existing(session, user.id, newest, row, settings)
    return LatestGame(game=row, existing_game_id=existing)


def _linked(session: Session, user_id: str) -> list[tuple[Platform, str]]:
    row = session.get(UserSettingsRow, user_id)
    if row is None:
        return []
    pairs: list[tuple[Platform, str | None]] = [
        ("chesscom", row.chesscom_username),
        ("lichess", row.lichess_username),
    ]
    return [(platform, name) for platform, name in pairs if name]


def _existing(
    session: Session, user_id: str, game: ImportedGame, row: ImportRow, settings: Settings
) -> str | None:
    """The player's stored copy of this game: same platform id, else the same moves."""
    if not row.already_imported:
        return None
    match = find_external(session, user_id, game.platform, game.external_id)
    if match is None and row.pgn is not None:
        limits = settings.limits
        parsed = parse_pgn(row.pgn, max_chars=limits.max_pgn_chars, max_plies=limits.max_plies)
        match = find_duplicate(session, user_id, game_fingerprint(parsed))
    return match.id if match else None


def fetch_recent(
    request: Request,
    session: Session,
    user_id: str,
    settings: Settings,
    platform: Platform,
    max_games: int,
    category: TimeControl | None = None,
    since: date | None = None,
) -> tuple[str, list[ImportedGame]]:
    """The player's username on `platform` and their latest games there, after the cooldown.
    Platform failures become HTTP errors with a message the player can act on."""
    username = _username(session, user_id, platform)
    _cool_down(session, user_id, settings)
    query = ImportQuery(username, max_games, category, since)
    transport = getattr(request.app.state, "import_transport", None)  # tests fake the platforms
    try:
        return username, fetch_games(platform, query, settings.imports, transport)
    except ImportFailure as failure:
        raise HTTPException(FAILURE_STATUS[failure.kind], detail=str(failure)) from failure


def _username(session: Session, user_id: str, platform: Platform) -> str:
    row = session.get(UserSettingsRow, user_id)
    name = (
        (row.lichess_username if platform == "lichess" else row.chesscom_username) if row else None
    )
    if not name:
        detail = f"Add your {PLATFORM_NAME[platform]} username on your profile first."
        raise HTTPException(status.HTTP_409_CONFLICT, detail=detail)
    return name


def _cool_down(session: Session, user_id: str, settings: Settings) -> None:
    """One import per player every few seconds, so the platforms aren't asked too often (kept in
    the database, SPEC_V4 §12.2)."""
    seconds = math.ceil(settings.imports.cooldown_seconds)
    if seconds > 0:
        check(
            session, f"import:{user_id}", 1, seconds, "Please wait {wait} before importing again."
        )


def _known(session: Session, user_id: str, platform: Platform) -> tuple[set[str], set[str]]:
    rows = session.execute(
        select(Game.external_source, Game.external_id, Game.fingerprint).where(
            Game.user_id == user_id
        )
    ).all()
    ids = {external_id for source, external_id, _ in rows if source == platform and external_id}
    prints = {fingerprint for _, _, fingerprint in rows if fingerprint}
    return ids, prints


def _row(
    index: int,
    game: ImportedGame,
    settings: Settings,
    usernames: list[str],
    known_ids: set[str],
    known_prints: set[str],
) -> ImportRow:
    error: PgnErrorDetail | None = None
    try:
        parsed = parse_pgn(
            game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
        )
    except PgnError as failure:
        parsed = None
        error = PgnErrorDetail(
            code=failure.code, message=failure.message, move_number=failure.move_number
        )
    headers = parsed.headers if parsed else {}
    seen = game.external_id in known_ids or (
        parsed is not None and game_fingerprint(parsed) in known_prints
    )
    return ImportRow(
        index=index,
        platform=game.platform,
        external_id=game.external_id,
        url=game.url,
        pgn=parsed.pgn if parsed else None,
        white=headers.get("White"),
        black=headers.get("Black"),
        result=headers.get("Result"),
        date=headers.get("UTCDate") or headers.get("Date"),
        time_control=headers.get("TimeControl"),
        category=cast(
            TimeControl | None,
            time_control_category(headers.get("TimeControl"), settings.onboarding),
        ),
        user_color=detect_color(parsed, usernames),
        already_imported=seen,
        error=error,
    )
