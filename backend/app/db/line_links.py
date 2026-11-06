"""Line links (SPEC_V3 §9.4): stored when a coach message is written, read for playback."""

from collections.abc import Sequence

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.coach.markup import LineLink
from app.db.models import LineLinkRow


def save_line_links(
    session: Session, user_id: str, game_id: str, message: str, links: Sequence[LineLink]
) -> None:
    """Store a message's links under the ids the message carries (the caller commits)."""
    for link in links:
        session.add(
            LineLinkRow(
                id=link.line_id,
                user_id=user_id,
                game_id=game_id,
                message=message,
                source=link.ref,
                kind=link.kind,
                label=link.label,
                start_path=link.start_path_uci,
                moves=link.moves_uci,
            )
        )


def load_line_link(session: Session, user_id: str, line_id: str) -> LineLinkRow | None:
    """The player's own link, or None (another player's link is as good as missing)."""
    row = session.get(LineLinkRow, line_id)
    return row if row is not None and row.user_id == user_id else None


def delete_line_links(session: Session, game_id: str) -> None:
    session.execute(delete(LineLinkRow).where(LineLinkRow.game_id == game_id))
