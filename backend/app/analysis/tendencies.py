"""Tendency tracking (SPEC_V2 §9.2): the player's mistake themes across games, weighted toward
recent games. Pure: the database builds `GameFacts`, this does the math."""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.analysis.detectors.types import Severity, ThemeName
from app.analysis.evals import Color
from app.analysis.phase import PHASES, Phase
from app.config import TendencySettings

Trend = Literal["improving", "worsening", "steady"]

THEME_LABELS: dict[ThemeName, str] = {
    "hung_piece": "Leaving pieces undefended",
    "allowed_tactic": "Allowing tactics",
    "missed_tactic": "Missing tactics",
    "missed_capture_or_check": "Missing captures and checks",
    "king_safety": "Weakening the king",
    "pawn_structure": "Creating pawn weaknesses",
    "endgame_technique": "Endgame technique",
    "slow_development": "Slow development",
    "time_trouble": "Mistakes in time trouble",
}

ROUND = 2


class FactRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    theme: ThemeName
    severity: Severity
    ply: int | None  # None for game-level facts
    move_number: int | None
    move_san: str | None


class GameFacts(BaseModel):
    """One analyzed game of the player's: what tendencies are computed from."""

    model_config = ConfigDict(frozen=True)

    game_id: str
    played_at: datetime  # the PGN date, else the upload time
    uploaded_at: datetime  # breaks ties: PGN dates often have no time of day
    user_color: Color
    accuracy: float | None
    phase_accuracy: dict[Phase, float | None]
    facts: list[FactRecord]


class Example(BaseModel):
    game_id: str
    move_number: int | None  # None for a game-level theme
    move_san: str | None


class Tendency(BaseModel):
    theme: ThemeName
    label: str
    rate_per_game: float  # weighted occurrences per game
    score: float  # weighted severity per game: what tendencies are ranked by
    trend: Trend | None  # None until there are enough games to compare
    games_seen: int
    provisional: bool
    recent_example: Example


class AccuracyReport(BaseModel):
    overall: float | None
    by_color: dict[Color, float | None]
    by_phase: dict[Phase, float | None]


class TendencyReport(BaseModel):
    games_analyzed: int
    provisional: bool
    tendencies: list[Tendency]  # every theme seen, highest score first
    accuracy: AccuracyReport


class WeightedGame(BaseModel):
    game: GameFacts
    age: int  # 0 = the most recent game
    weight: float


class ThemeSums(BaseModel):
    """One theme's per-game counts and the sums behind its rate and score."""

    theme: ThemeName
    counts: list[int]  # per game, in age order
    severity: list[float]  # per game: the facts' severity weights, summed
    weighted_count: float  # sum of w * count
    weighted_severity: float  # sum of w * severity


def weigh(games: Sequence[GameFacts], settings: TendencySettings) -> list[WeightedGame]:
    """The games most recent first, each weighted 0.5 ** (age / half-life)."""
    ordered = sorted(games, key=lambda g: (g.played_at, g.uploaded_at, g.game_id), reverse=True)
    return [
        WeightedGame(game=game, age=age, weight=0.5 ** (age / settings.half_life_games))
        for age, game in enumerate(ordered)
    ]


def counted(facts: Sequence[FactRecord], settings: TendencySettings) -> list[FactRecord]:
    """The facts that count toward tendencies: game-level notes are always-on summaries."""
    return [f for f in facts if settings.severity_weights.get(f.severity, 0) > 0]


def theme_sums(weighted: Sequence[WeightedGame], settings: TendencySettings) -> list[ThemeSums]:
    """Per theme and game: a per-move theme counts each occurrence, a game-level theme 1."""
    weights = settings.severity_weights
    themes = sorted({f.theme for g in weighted for f in counted(g.game.facts, settings)})
    sums = []
    for theme in themes:
        counts: list[int] = []
        severity: list[float] = []
        for game in weighted:
            facts = [f for f in counted(game.game.facts, settings) if f.theme == theme]
            per_move = [f for f in facts if f.ply is not None]
            if per_move:
                counts.append(len(per_move))
                severity.append(sum(weights[f.severity] for f in per_move))
            else:  # game-level: flagged once, or not at all
                counts.append(1 if facts else 0)
                severity.append(max((weights[f.severity] for f in facts), default=0))
        sums.append(
            ThemeSums(
                theme=theme,
                counts=counts,
                severity=severity,
                weighted_count=_dot(weighted, counts),
                weighted_severity=_dot(weighted, severity),
            )
        )
    return sums


def aggregate(games: Sequence[GameFacts], settings: TendencySettings) -> TendencyReport:
    weighted = weigh(games, settings)
    total = sum(g.weight for g in weighted)
    provisional = len(weighted) < settings.provisional_below_games
    tendencies = [
        Tendency(
            theme=sums.theme,
            label=THEME_LABELS[sums.theme],
            rate_per_game=round(sums.weighted_count / total, ROUND),
            score=round(sums.weighted_severity / total, ROUND),
            trend=trend(weighted, sums.counts, settings),
            games_seen=sum(c > 0 for c in sums.counts),
            provisional=provisional,
            recent_example=_example(weighted, sums, settings),
        )
        for sums in theme_sums(weighted, settings)
    ]
    tendencies.sort(key=lambda t: (-t.score, -t.rate_per_game, t.theme))
    return TendencyReport(
        games_analyzed=len(weighted),
        provisional=provisional,
        tendencies=tendencies,
        accuracy=accuracy_report(weighted),
    )


def trend(
    weighted: Sequence[WeightedGame], counts: Sequence[int], settings: TendencySettings
) -> Trend | None:
    """The weighted rate over the last N games against the N before; None with fewer than 2N
    games. More occurrences per game is worse."""
    n = settings.trend_window_games
    if len(weighted) < 2 * n:
        return None
    recent = _dot(weighted[:n], counts[:n]) / sum(g.weight for g in weighted[:n])
    before = _dot(weighted[n : 2 * n], counts[n : 2 * n]) / sum(
        g.weight for g in weighted[n : 2 * n]
    )
    if recent - before > settings.trend_margin:
        return "worsening"
    if before - recent > settings.trend_margin:
        return "improving"
    return "steady"


def accuracy_report(weighted: Sequence[WeightedGame]) -> AccuracyReport:
    """Weighted mean accuracy over the games that have one: overall, by color, and by phase."""
    colors: tuple[Color, ...] = ("white", "black")
    return AccuracyReport(
        overall=_mean([(g.weight, g.game.accuracy) for g in weighted]),
        by_color={
            color: _mean(
                [(g.weight, g.game.accuracy) for g in weighted if g.game.user_color == color]
            )
            for color in colors
        },
        by_phase={
            phase: _mean([(g.weight, g.game.phase_accuracy.get(phase)) for g in weighted])
            for phase in PHASES
        },
    )


def _dot(weighted: Sequence[WeightedGame], values: Sequence[float]) -> float:
    return sum(g.weight * v for g, v in zip(weighted, values, strict=True))


def _mean(values: Sequence[tuple[float, float | None]]) -> float | None:
    known = [(w, v) for w, v in values if v is not None]
    if not known:
        return None
    return round(sum(w * v for w, v in known) / sum(w for w, _ in known), 1)


def _example(
    weighted: Sequence[WeightedGame], sums: ThemeSums, settings: TendencySettings
) -> Example:
    """The theme's most recent occurrence: its most severe fact in the latest game it was in."""
    game = next(g.game for g, c in zip(weighted, sums.counts, strict=True) if c > 0)
    facts = [f for f in counted(game.facts, settings) if f.theme == sums.theme]
    fact = min(facts, key=lambda f: (-settings.severity_weights[f.severity], f.ply or 0))
    return Example(game_id=game.game_id, move_number=fact.move_number, move_san=fact.move_san)
