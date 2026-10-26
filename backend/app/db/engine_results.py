"""Persistence for engine results."""

from collections.abc import Collection, Sequence
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.engine import EngineLine, EngineResult, Tier
from app.db.models import EngineResultRow


def save_results(session: Session, game_id: str, results: Sequence[EngineResult]) -> None:
    """Store results, replacing any earlier result for the same position and tier."""
    for tier in {result.tier for result in results}:
        fens = [result.fen for result in results if result.tier == tier]
        session.execute(
            delete(EngineResultRow).where(
                EngineResultRow.game_id == game_id,
                EngineResultRow.tier == tier,
                EngineResultRow.fen.in_(fens),
            )
        )
    session.add_all(
        EngineResultRow(
            game_id=game_id,
            ply=result.ply,
            fen=result.fen,
            tier=result.tier,
            depth=result.depth,
            time_ms=result.time_ms,
            lines=[line.model_dump() for line in result.lines],
        )
        for result in results
    )
    session.commit()


def load_results(session: Session, game_id: str, tiers: Collection[Tier]) -> list[EngineResult]:
    rows = session.scalars(
        select(EngineResultRow)
        .where(EngineResultRow.game_id == game_id, EngineResultRow.tier.in_(tiers))
        .order_by(EngineResultRow.id)
    )
    return [
        EngineResult(
            ply=row.ply,
            fen=row.fen,
            tier=cast(Tier, row.tier),  # only validated tiers are ever stored
            depth=row.depth,
            time_ms=row.time_ms,
            lines=[EngineLine.model_validate(line) for line in row.lines],
        )
        for row in rows
    ]
