"""The dashboard (SPEC_V3 §8.1): pure aggregation over per-game rows the database already holds
(`game_stats`, PLAN_V3 adjustment 6), the latest tendency report and the tendency snapshots.
No LLM, no engine, no summary parsing."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.analysis.evals import Color
from app.analysis.tendencies import TendencyReport, Trend
from app.config import PuzzleSettings

Range = Literal["10", "25", "all"]
Result = Literal["win", "loss", "draw"]
ROLLING_GAMES = 10  # SPEC_V3 §8.1: a rolling average of the last 10 games
RECENT_GAMES = 10
FOCUS_AREAS = 3
CHART_THEMES = 5
CONTINUE_GAMES = 5


@dataclass(frozen=True)
class GameRow:
    """One analyzed game of the player; `build` takes them most recent first."""

    game_id: str
    played_at: datetime
    opponent: str
    color: Color
    result: Result | None
    accuracy: float | None
    accuracy_opening: float | None
    accuracy_middlegame: float | None
    accuracy_endgame: float | None
    moments_total: int
    moments_done: int


class PuzzleLink(BaseModel):
    theme: str
    label: str
    url: str


class FocusArea(BaseModel):
    theme: str
    label: str
    trend: Trend | None
    rate_per_game: float
    games_seen: int
    example_game_id: str | None
    example_move: str | None  # "14. Nd4", the "See an example" link's detail
    example_ply: int | None  # where to open the game
    puzzles: list[PuzzleLink]


class ContinueGame(BaseModel):
    game_id: str
    opponent: str
    played_at: datetime
    moments_total: int
    moments_done: int


class ThemeSeries(BaseModel):
    theme: str
    label: str


class TrendPoint(BaseModel):
    games_analyzed: int
    date: datetime
    rates: dict[str, float]  # theme -> weighted rate per game


class MistakeTrend(BaseModel):
    themes: list[ThemeSeries]  # the top 5, worst first
    points: list[TrendPoint]  # oldest first


class AccuracyPoint(BaseModel):
    game_id: str
    played_at: datetime
    color: Color
    result: Result | None
    accuracy: float
    rolling: float  # average of this game and up to 9 before it


class AccuracyTrend(BaseModel):
    points: list[AccuracyPoint]  # oldest first
    by_phase: dict[str, float | None]  # opening / middlegame / endgame averages


class RecentGame(BaseModel):
    game_id: str
    played_at: datetime
    opponent: str
    color: Color
    result: Result | None
    accuracy: float | None
    moments_total: int
    moments_done: int


class OnboardingCard(BaseModel):
    complete: bool  # all 12 assessment games analyzed
    analyzed: int
    total: int
    has_report: bool


class Dashboard(BaseModel):
    games: int  # analyzed games matching the filters
    focus_areas: list[FocusArea]  # across all games: tendencies aren't filtered
    continue_games: list[ContinueGame]
    mistake_trend: MistakeTrend
    accuracy: AccuracyTrend
    recent: list[RecentGame]
    onboarding: OnboardingCard


@dataclass(frozen=True)
class Snapshot:
    games_analyzed: int
    created_at: datetime
    report: TendencyReport


def build(
    games: Sequence[GameRow],
    latest: TendencyReport | None,
    snapshots: Sequence[Snapshot],
    onboarding: OnboardingCard,
    example_colors: dict[str, Color],
    puzzles: PuzzleSettings,
    game_range: Range,
) -> Dashboard:
    """`games` are the filtered games, most recent first; `example_colors` gives the side the
    player had in each tendency's example game (to find the example move's ply)."""
    limit = None if game_range == "all" else int(game_range)
    shown = list(games[:limit])
    unfinished = [g for g in shown if g.moments_done < g.moments_total][:CONTINUE_GAMES]
    return Dashboard(
        games=len(shown),
        focus_areas=_focus(latest, example_colors, puzzles),
        continue_games=[
            ContinueGame(
                game_id=g.game_id,
                opponent=g.opponent,
                played_at=g.played_at,
                moments_total=g.moments_total,
                moments_done=g.moments_done,
            )
            for g in unfinished
        ],
        mistake_trend=_mistakes(latest, snapshots),
        accuracy=_accuracy(shown),
        recent=[
            RecentGame(
                game_id=g.game_id,
                played_at=g.played_at,
                opponent=g.opponent,
                color=g.color,
                result=g.result,
                accuracy=g.accuracy,
                moments_total=g.moments_total,
                moments_done=g.moments_done,
            )
            for g in shown[:RECENT_GAMES]
        ],
        onboarding=onboarding,
    )


def _focus(
    latest: TendencyReport | None, colors: dict[str, Color], puzzles: PuzzleSettings
) -> list[FocusArea]:
    if latest is None:
        return []
    areas = []
    for tendency in [t for t in latest.tendencies if not t.provisional][:FOCUS_AREAS]:
        example = tendency.recent_example
        move = ply = None
        color = colors.get(example.game_id)
        if example.move_number is not None and example.move_san and color is not None:
            black = color == "black"
            move = f"{example.move_number}{'...' if black else '. '}{example.move_san}"
            ply = (example.move_number - 1) * 2 + (2 if black else 1)
        slugs = [s for s in puzzles.for_theme.get(tendency.theme, []) if s in puzzles.themes]
        areas.append(
            FocusArea(
                theme=tendency.theme,
                label=tendency.label,
                trend=tendency.trend,
                rate_per_game=tendency.rate_per_game,
                games_seen=tendency.games_seen,
                example_game_id=example.game_id,
                example_move=move,
                example_ply=ply,
                puzzles=[
                    PuzzleLink(theme=s, label=puzzles.themes[s], url=puzzles.url.format(slug=s))
                    for s in slugs
                ],
            )
        )
    return areas


def _mistakes(latest: TendencyReport | None, snapshots: Sequence[Snapshot]) -> MistakeTrend:
    if latest is None:
        return MistakeTrend(themes=[], points=[])
    top = latest.tendencies[:CHART_THEMES]
    names = {t.theme for t in top}
    points = [
        TrendPoint(
            games_analyzed=s.games_analyzed,
            date=s.created_at,
            rates={t.theme: t.rate_per_game for t in s.report.tendencies if t.theme in names},
        )
        for s in snapshots
    ]
    themes = [ThemeSeries(theme=t.theme, label=t.label) for t in top]
    return MistakeTrend(themes=themes, points=points)


def _mean(values: Sequence[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return round(sum(known) / len(known), 1) if known else None


def _accuracy(games: Sequence[GameRow]) -> AccuracyTrend:
    rated = [(g, g.accuracy) for g in reversed(games) if g.accuracy is not None]  # oldest first
    points = []
    for i, (game, accuracy) in enumerate(rated):
        window = [a for _, a in rated[max(0, i - ROLLING_GAMES + 1) : i + 1]]
        points.append(
            AccuracyPoint(
                game_id=game.game_id,
                played_at=game.played_at,
                color=game.color,
                result=game.result,
                accuracy=accuracy,
                rolling=round(sum(window) / len(window), 1),
            )
        )
    return AccuracyTrend(
        points=points,
        by_phase={
            "opening": _mean([g.accuracy_opening for g in games]),
            "middlegame": _mean([g.accuracy_middlegame for g in games]),
            "endgame": _mean([g.accuracy_endgame for g in games]),
        },
    )
