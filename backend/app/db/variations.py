"""The player's saved variations per game (SPEC_V3 §5.1). The browser sends its whole list on
every save (checked by app.analysis.variations); it replaces the old one, in the order sent."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.variations import SavedVariation
from app.db.models import Game, GameVariationRow


def load_variations(session: Session, game: Game) -> list[SavedVariation] | None:
    """The saved variations in display order, or None if the player never saved any."""
    if game.variations_saved_at is None:
        return None
    rows = session.scalars(
        select(GameVariationRow)
        .where(GameVariationRow.game_id == game.id)
        .order_by(GameVariationRow.position)
    ).all()
    return [SavedVariation(start_path=row.start_path, moves=row.moves) for row in rows]


def save_variations(
    session: Session, game: Game, user_id: str, variations: Sequence[SavedVariation]
) -> None:
    """Replace the game's variations with `variations` (already checked), keeping when each
    unchanged one was first saved."""
    old = {
        (tuple(row.start_path), tuple(row.moves)): row.created_at
        for row in session.scalars(
            select(GameVariationRow).where(GameVariationRow.game_id == game.id)
        )
    }
    session.execute(delete(GameVariationRow).where(GameVariationRow.game_id == game.id))
    now = datetime.now(UTC)
    for position, variation in enumerate(variations):
        key = (tuple(variation.start_path), tuple(variation.moves))
        session.add(
            GameVariationRow(
                game_id=game.id,
                user_id=user_id,
                position=position,
                start_path=list(variation.start_path),
                moves=list(variation.moves),
                created_at=old.get(key, now),
                updated_at=now,
            )
        )
    game.variations_saved_at = game.variations_saved_at or now
    session.commit()


def delete_variations(session: Session, game_id: str) -> None:
    session.execute(delete(GameVariationRow).where(GameVariationRow.game_id == game_id))
