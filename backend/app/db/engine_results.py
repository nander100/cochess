"""Persistence for engine results and game summaries."""

from collections.abc import Collection, Sequence
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.engine import EngineLine, EngineResult, Tier
from app.analysis.summary_models import GameSummary
from app.db.models import EngineResultRow, Game, GameSummaryRow


def save_results(session: Session, game_id: str, results: Sequence[EngineResult]) -> None:
    """Store results, replacing any earlier result for the same position and tier. Results are
    tagged with the game's owner: browser results are never shared across users (SPEC_V2 §4.2)."""
    game = session.get(Game, game_id)
    user_id = game.user_id if game is not None else None
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
            user_id=user_id,
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


def save_summary(session: Session, game_id: str, summary: GameSummary) -> None:
    session.merge(GameSummaryRow(game_id=game_id, summary=summary.model_dump(mode="json")))
    session.commit()


def load_summary(session: Session, game_id: str) -> GameSummary | None:
    row = session.get(GameSummaryRow, game_id)
    return None if row is None else GameSummary.model_validate(row.summary)
