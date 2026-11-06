"""The annotation log (SPEC_V3 §6.2): every board-tag shape the coach wrote that wasn't drawn."""

import logging
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.coach.annotations import Dropped
from app.db.models import AnnotationLogRow

logger = logging.getLogger(__name__)


def log_dropped(
    session: Session,
    *,
    user_id: str | None,
    game_id: str | None,
    task: str,
    dropped: Sequence[Dropped],
    moment_index: int | None = None,
) -> None:
    """Store and log each dropped shape (the caller commits)."""
    for item in dropped:
        session.add(
            AnnotationLogRow(
                user_id=user_id,
                game_id=game_id,
                task=task,
                moment_index=moment_index,
                tag=item.tag,
                shape=item.shape,
                reason=item.reason,
            )
        )
    if dropped:
        logger.warning(
            "annotations dropped: game=%s task=%s reasons=%s",
            game_id,
            task,
            sorted({d.reason for d in dropped}),
        )
