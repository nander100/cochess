"""The walkthrough cache (SPEC_V3 §7.2 step 6): per player, by start position and line."""

from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import LlmUsageRow, WalkthroughRow


def line_key(line_uci: Sequence[str]) -> str:
    return " ".join(line_uci)


def load_walkthrough(
    session: Session, user_id: str, start_fen: str, line_uci: Sequence[str]
) -> WalkthroughRow | None:
    return session.scalars(
        select(WalkthroughRow).where(
            WalkthroughRow.user_id == user_id,
            WalkthroughRow.start_fen == start_fen,
            WalkthroughRow.line_key == line_key(line_uci),
        )
    ).first()


def save_walkthrough(
    session: Session,
    *,
    user_id: str,
    game_id: str,
    start_path: list[str],
    start_fen: str,
    line_uci: Sequence[str],
    steps: dict[str, object],
) -> None:
    """Store (or replace) one walkthrough, and commit."""
    existing = load_walkthrough(session, user_id, start_fen, line_uci)
    if existing is not None:
        session.delete(existing)
        session.flush()
    session.add(
        WalkthroughRow(
            user_id=user_id,
            game_id=game_id,
            start_path=start_path,
            start_fen=start_fen,
            line_key=line_key(line_uci),
            steps=steps,
        )
    )
    session.commit()


def delete_walkthroughs(session: Session, game_id: str) -> None:
    session.execute(delete(WalkthroughRow).where(WalkthroughRow.game_id == game_id))


def walkthroughs_written(session: Session, game_id: str) -> int:
    """Walkthrough coach calls made for a game (retries included), for the per-game limit."""
    count = session.scalar(
        select(func.count())
        .select_from(LlmUsageRow)
        .where(LlmUsageRow.game_id == game_id, LlmUsageRow.task == "walkthrough")
    )
    return int(count or 0)
