"""Onboarding games and baseline reports (SPEC_V2 §10), always for one player."""

from collections import Counter
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.onboarding import Slot
from app.db.models import BaselineReportRow, Game

_SLOT_OF: dict[tuple[str, str | None], Slot] = {
    ("white", "win"): "white_win",
    ("white", "loss"): "white_loss",
    ("black", "win"): "black_win",
    ("black", "loss"): "black_loss",
}


def onboarding_games(session: Session, user_id: str) -> list[Game]:
    """The player's onboarding games, in upload order (the order they're analyzed)."""
    return list(
        session.scalars(
            select(Game)
            .where(Game.user_id == user_id, Game.source == "onboarding")
            .order_by(Game.created_at, Game.id)
        )
    )


def slot_of(game: Game) -> Slot:
    """An onboarding game's slot. Only games that filled a slot are stored as onboarding games."""
    return _SLOT_OF[(game.user_color, game.user_result)]


def filled_slots(games: Sequence[Game]) -> Counter[Slot]:
    return Counter(slot_of(game) for game in games)


def save_report(
    session: Session, user_id: str, text: str, removed: list[str], game_ids: list[str]
) -> BaselineReportRow:
    row = BaselineReportRow(
        user_id=user_id, text=text, invalid_moves_removed=removed, game_ids=game_ids
    )
    session.add(row)
    session.commit()
    return row


def latest_report(session: Session, user_id: str) -> BaselineReportRow | None:
    return session.scalars(
        select(BaselineReportRow)
        .where(BaselineReportRow.user_id == user_id)
        .order_by(BaselineReportRow.created_at.desc(), BaselineReportRow.id.desc())
        .limit(1)
    ).first()
