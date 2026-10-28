"""Game access, always scoped to one user (SPEC_V2 §4.2): another user's game is "not found"."""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.analysis.evals import Color
from app.analysis.game_info import fingerprint, played_at, user_result
from app.analysis.pgn import ParsedGame, parse_pgn
from app.analysis.summary import build_summary
from app.analysis.summary_models import GameSummary, UserInfo
from app.config import Settings
from app.db.engine_results import load_results, save_summary
from app.db.models import EngineResultRow, Game, GameSummaryRow, LlmUsageRow, User
from app.db.tendencies import refresh_tendencies, save_theme_facts


class GameNotFoundError(Exception):
    pass


def get_game(session: Session, user_id: str, game_id: str) -> Game:
    game = session.get(Game, game_id)
    if game is None or game.user_id != user_id:
        raise GameNotFoundError(game_id)
    return game


def new_game(
    session: Session,
    user: User,
    parsed: ParsedGame,
    color: Color,
    *,
    source: str,
    category: str | None = None,
) -> Game:
    """Store an uploaded game for `user` (the caller commits). Elo and playstyle are the
    profile's at upload: the Elo at analysis, kept even if the profile changes later."""
    now = datetime.now(UTC)
    game = Game(
        user_id=user.id,
        pgn=parsed.pgn,
        user_color=color,
        elo=user.elo,
        playstyle=user.playstyle,
        headers=parsed.headers,
        played_at=played_at(parsed.headers) or now,
        user_result=user_result(parsed.headers.get("Result"), color),
        time_control_category=category,
        source=source,
        fingerprint=game_fingerprint(parsed),
        created_at=now,
    )
    session.add(game)
    return game


def game_fingerprint(parsed: ParsedGame) -> str:
    return fingerprint(parsed.headers, [p.uci for p in parsed.positions])


def find_duplicate(session: Session, user_id: str, key: str) -> Game | None:
    """The player's game with this fingerprint, if they've uploaded it before."""
    return session.scalars(
        select(Game).where(Game.user_id == user_id, Game.fingerprint == key).limit(1)
    ).first()


def fill_fingerprints(session: Session, settings: Settings) -> list[list[Game]]:
    """Fingerprint games uploaded before fingerprints existed. Returns the duplicate groups this
    reveals (same player, same fingerprint), oldest upload first, for the owner to review."""
    for game in session.scalars(select(Game).where(Game.fingerprint.is_(None))):
        parsed = parse_pgn(
            game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
        )
        game.fingerprint = game_fingerprint(parsed)
    session.commit()
    groups: dict[tuple[str | None, str | None], list[Game]] = {}
    for game in session.scalars(select(Game).order_by(Game.created_at)):
        groups.setdefault((game.user_id, game.fingerprint), []).append(game)
    return [games for games in groups.values() if len(games) > 1]


def assign_unowned_games(session: Session, user: User) -> int:
    """Give every game without an owner (v1 games) to `user`, with the facts v1 didn't store.
    Returns how many games were assigned."""
    games = list(session.scalars(select(Game).where(Game.user_id.is_(None))))
    for game in games:
        game.user_id = user.id
        game.played_at = played_at(game.headers) or game.created_at
        game.user_result = user_result(game.headers.get("Result"), cast(Color, game.user_color))
    ids = [game.id for game in games]
    for table in (EngineResultRow, LlmUsageRow):
        session.execute(
            update(table)
            .where(table.game_id.in_(ids), table.user_id.is_(None))
            .values(user_id=user.id)
        )
    session.commit()
    return len(games)


def list_games(session: Session, user_id: str) -> list[tuple[Game, float | None]]:
    """The player's games, most recently played first, with the player's accuracy if analyzed."""
    rows = session.execute(
        select(Game, GameSummaryRow.summary)
        .outerjoin(GameSummaryRow, GameSummaryRow.game_id == Game.id)
        .where(Game.user_id == user_id)
        .order_by(Game.played_at.desc(), Game.created_at.desc())
    )
    return [(game, _user_accuracy(summary)) for game, summary in rows]


def _user_accuracy(summary: dict[str, Any] | None) -> float | None:
    accuracy = (summary or {}).get("accuracy") or {}
    value = accuracy.get("user")
    return float(value) if isinstance(value, int | float) else None


def record_analysis(session: Session, settings: Settings, game: Game, summary: GameSummary) -> None:
    """Store an analyzed game's summary and theme facts, then refresh the player's tendencies
    (SPEC_V2 §9.2: recomputed after every analyzed game). The caller commits."""
    save_summary(session, game.id, summary)
    save_theme_facts(session, game, summary)
    game.status = "analyzed"
    if game.user_id is not None:
        refresh_tendencies(session, settings.tendencies, game.user_id)


def rebuild_summaries(session: Session, settings: Settings, user: User | None = None) -> int:
    """Rebuild every analyzed game's summary (or one player's) from its stored engine results,
    so summaries made by older code gain what's been added since (e.g. moments, theme facts).
    No engine runs. Each player's tendencies are refreshed once at the end. Returns how many
    were rebuilt."""
    query = select(Game).where(Game.status == "analyzed")
    if user is not None:
        query = query.where(Game.user_id == user.id)
    games = list(session.scalars(query))
    for game in games:
        parsed = parse_pgn(
            game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
        )
        info = UserInfo(color=cast(Color, game.user_color), elo=game.elo, playstyle=game.playstyle)
        results = load_results(session, game.id, ["scan", "verify"])
        summary = build_summary(parsed, results, info, settings)
        save_summary(session, game.id, summary)
        save_theme_facts(session, game, summary)
    for user_id in sorted({game.user_id for game in games if game.user_id is not None}):
        refresh_tendencies(session, settings.tendencies, user_id)
    session.commit()
    return len(games)
