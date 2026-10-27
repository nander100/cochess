"""Game access, always scoped to one user (SPEC_V2 §4.2): another user's game is "not found"."""

from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.analysis.evals import Color
from app.analysis.game_info import played_at, user_result
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
