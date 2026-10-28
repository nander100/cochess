"""Theme facts and tendency snapshots (SPEC_V2 §9), always for one player."""

from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.detectors.types import DetailValue, Severity, ThemeName
from app.analysis.evals import Color
from app.analysis.summary_models import GameSummary
from app.analysis.tendencies import FactRecord, GameFacts, TendencyReport, aggregate
from app.config import TendencySettings
from app.db.models import Game, GameSummaryRow, GameThemeFactRow, TendencySnapshotRow


def save_theme_facts(session: Session, game: Game, summary: GameSummary) -> None:
    """Replace the game's theme-fact rows with the summary's. A v1 game without an owner yet has
    none: its facts are written when `cli backfill` runs after `assign-games`."""
    session.execute(delete(GameThemeFactRow).where(GameThemeFactRow.game_id == game.id))
    if game.user_id is None:
        return
    phases = {move.ply: move.phase for move in summary.move_list}
    session.add_all(
        GameThemeFactRow(
            user_id=game.user_id,
            game_id=game.id,
            theme=fact.theme,
            subtype=_subtype(fact.details),
            ply=fact.ply,
            move_number=fact.move_number,
            move_san=fact.move_san,
            severity=fact.severity,
            phase=phases.get(fact.ply) if fact.ply is not None else None,
            user_color=summary.user.color,
            details=dict(fact.details),
        )
        for fact in summary.theme_facts
    )


def _subtype(details: dict[str, DetailValue]) -> str | None:
    value = details.get("subtype", details.get("weakness"))
    return value if isinstance(value, str) else None


def game_facts(session: Session, user_id: str) -> list[GameFacts]:
    """The player's analyzed games, each with its accuracy and theme facts."""
    rows = session.execute(
        select(Game, GameSummaryRow.summary)
        .join(GameSummaryRow, GameSummaryRow.game_id == Game.id)
        .where(Game.user_id == user_id, Game.status == "analyzed")
    ).all()
    facts: dict[str, list[FactRecord]] = {}
    for row in session.scalars(
        select(GameThemeFactRow)
        .where(GameThemeFactRow.user_id == user_id)
        .order_by(GameThemeFactRow.id)
    ):
        facts.setdefault(row.game_id, []).append(
            FactRecord(
                theme=cast(ThemeName, row.theme),
                severity=cast(Severity, row.severity),
                ply=row.ply,
                move_number=row.move_number,
                move_san=row.move_san,
            )
        )
    games = []
    for game, data in rows:
        summary = GameSummary.model_validate(data)
        games.append(
            GameFacts(
                game_id=game.id,
                played_at=game.played_at or game.created_at,
                user_color=cast(Color, game.user_color),
                accuracy=summary.accuracy.user,
                phase_accuracy={
                    phase: stats.accuracy for phase, stats in summary.phase_breakdown.items()
                },
                facts=facts.get(game.id, []),
            )
        )
    return games


def refresh_tendencies(
    session: Session, settings: TendencySettings, user_id: str
) -> TendencyReport:
    """Recompute the player's tendencies and save them as a new snapshot (SPEC_V2 §9.2)."""
    report = aggregate(game_facts(session, user_id), settings)
    session.add(
        TendencySnapshotRow(
            user_id=user_id,
            games_analyzed=report.games_analyzed,
            report=report.model_dump(mode="json"),
        )
    )
    return report


def latest_tendencies(session: Session, user_id: str) -> TendencyReport | None:
    row = session.scalars(
        select(TendencySnapshotRow)
        .where(TendencySnapshotRow.user_id == user_id)
        .order_by(TendencySnapshotRow.created_at.desc(), TendencySnapshotRow.id.desc())
        .limit(1)
    ).first()
    return None if row is None else TendencyReport.model_validate(row.report)
