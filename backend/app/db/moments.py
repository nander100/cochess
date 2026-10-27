"""Persistence for critical-moment progress (SPEC_V2 §8.2)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MomentProgressRow


def load_progress(session: Session, game_id: str) -> dict[int, MomentProgressRow]:
    rows = session.scalars(select(MomentProgressRow).where(MomentProgressRow.game_id == game_id))
    return {row.moment_index: row for row in rows}


def progress_for(session: Session, user_id: str, game_id: str, index: int) -> MomentProgressRow:
    """This moment's progress, created (state "intro", nothing tried) the first time."""
    row = session.scalars(
        select(MomentProgressRow).where(
            MomentProgressRow.game_id == game_id, MomentProgressRow.moment_index == index
        )
    ).first()
    if row is None:
        row = MomentProgressRow(
            user_id=user_id,
            game_id=game_id,
            moment_index=index,
            state="intro",
            attempts=[],
            revealed=False,
            messages=[],
            leaks=0,
        )
        session.add(row)
        session.flush()
    return row
