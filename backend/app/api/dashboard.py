"""The dashboard (SPEC_V3 §8.1): `GET /api/dashboard?tc=&color=&range=`, everything the home page
shows in one response, computed from stored numbers (no LLM, no engine, no summary parsing)."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.dashboard import (
    Dashboard,
    GameRow,
    OnboardingCard,
    Range,
    Result,
    Snapshot,
    build,
)
from app.analysis.evals import Color
from app.analysis.onboarding import SLOTS
from app.analysis.summary_models import GameSummary
from app.analysis.tendencies import TendencyReport
from app.api.deps import get_app_settings, get_session
from app.api.schemas import TimeControl
from app.auth.deps import CurrentUser
from app.config import Settings
from app.db.engine_results import stats_row
from app.db.models import (
    Game,
    GameStatsRow,
    GameSummaryRow,
    MomentProgressRow,
    TendencySnapshotRow,
)
from app.db.onboarding import filled_slots, latest_report, onboarding_games

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@router.get("")
def dashboard(
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    tc: Annotated[TimeControl | None, Query()] = None,
    color: Annotated[Color | None, Query()] = None,
    game_range: Annotated[Range, Query(alias="range")] = "all",
) -> Dashboard:
    _fill_missing_stats(session, user.id)
    snapshots = _snapshots(session, user.id)
    latest = snapshots[-1].report if snapshots else None
    return build(
        _games(session, user.id, tc, color),
        latest,
        snapshots,
        _onboarding(session, user.id, settings),
        _example_colors(session, user.id, latest),
        settings.puzzles,
        game_range,
    )


def _fill_missing_stats(session: Session, user_id: str) -> None:
    """Games analyzed before `game_stats` existed get their row once, from the stored summary."""
    missing = session.execute(
        select(Game.id, GameSummaryRow.summary)
        .join(GameSummaryRow, GameSummaryRow.game_id == Game.id)
        .outerjoin(GameStatsRow, GameStatsRow.game_id == Game.id)
        .where(Game.user_id == user_id, GameStatsRow.game_id.is_(None))
    ).all()
    for game_id, summary in missing:
        session.merge(stats_row(game_id, user_id, GameSummary.model_validate(summary)))
    if missing:
        session.commit()


def _games(
    session: Session, user_id: str, tc: TimeControl | None, color: Color | None
) -> list[GameRow]:
    query = (
        select(Game, GameStatsRow)
        .join(GameStatsRow, GameStatsRow.game_id == Game.id)
        .where(Game.user_id == user_id, Game.status == "analyzed")
        .order_by(Game.played_at.desc(), Game.created_at.desc())
    )
    if tc is not None:
        query = query.where(Game.time_control_category == tc)
    if color is not None:
        query = query.where(Game.user_color == color)
    finished_rows = session.execute(
        select(MomentProgressRow.game_id, func.count())
        .where(
            MomentProgressRow.user_id == user_id,
            MomentProgressRow.state.in_(["solved", "revealed"]),
        )
        .group_by(MomentProgressRow.game_id)
    ).all()
    finished: dict[str, int] = {game_id: count for game_id, count in finished_rows}
    rows = []
    for game, stats in session.execute(query).all():
        played = cast(Color, game.user_color)
        rows.append(
            GameRow(
                game_id=game.id,
                played_at=game.played_at or game.created_at,
                opponent=game.headers.get("Black" if played == "white" else "White", "?"),
                color=played,
                result=cast(Result | None, game.user_result),
                accuracy=stats.accuracy,
                accuracy_opening=stats.accuracy_opening,
                accuracy_middlegame=stats.accuracy_middlegame,
                accuracy_endgame=stats.accuracy_endgame,
                moments_total=stats.moments_total,
                moments_done=min(finished.get(game.id, 0), stats.moments_total),
            )
        )
    return rows


def _snapshots(session: Session, user_id: str) -> list[Snapshot]:
    """The tendency history, oldest first; the last is the latest report."""
    rows = session.scalars(
        select(TendencySnapshotRow)
        .where(TendencySnapshotRow.user_id == user_id)
        .order_by(TendencySnapshotRow.created_at, TendencySnapshotRow.id)
    ).all()
    return [
        Snapshot(r.games_analyzed, r.created_at, TendencyReport.model_validate(r.report))
        for r in rows
    ]


def _example_colors(
    session: Session, user_id: str, latest: TendencyReport | None
) -> dict[str, Color]:
    """The side the player had in each focus area's example game: where its move is."""
    if latest is None:
        return {}
    ids = {t.recent_example.game_id for t in latest.tendencies}
    rows = session.execute(
        select(Game.id, Game.user_color).where(Game.user_id == user_id, Game.id.in_(ids))
    ).all()
    return {game_id: cast(Color, color) for game_id, color in rows}


def _onboarding(session: Session, user_id: str, settings: Settings) -> OnboardingCard:
    games = onboarding_games(session, user_id)
    filled = filled_slots(games)
    per_slot = settings.onboarding.games_per_slot
    analyzed = sum(game.status == "analyzed" for game in games)
    complete = all(filled[slot] >= per_slot for slot in SLOTS) and analyzed == len(games)
    return OnboardingCard(
        complete=complete,
        analyzed=analyzed,
        total=per_slot * len(SLOTS),
        has_report=latest_report(session, user_id) is not None,
    )
