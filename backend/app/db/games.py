"""Game access, always scoped to one user (SPEC_V2 §4.2): another user's game is "not found"."""

from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.analysis.evals import Color
from app.analysis.game_info import played_at, user_result
from app.analysis.pgn import parse_pgn
from app.analysis.summary import build_summary
from app.analysis.summary_models import UserInfo
from app.config import Settings
from app.db.engine_results import load_results, save_summary
from app.db.models import EngineResultRow, Game, GameSummaryRow, LlmUsageRow, User


class GameNotFoundError(Exception):
    pass


def get_game(session: Session, user_id: str, game_id: str) -> Game:
    game = session.get(Game, game_id)
    if game is None or game.user_id != user_id:
        raise GameNotFoundError(game_id)
    return game


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


def rebuild_summaries(session: Session, settings: Settings, user: User | None = None) -> int:
    """Rebuild every analyzed game's summary (or one player's) from its stored engine results,
    so summaries made by older code gain what's been added since (e.g. moments). No engine runs.
    Returns how many were rebuilt."""
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
        save_summary(session, game.id, build_summary(parsed, results, info, settings))
    return len(games)
