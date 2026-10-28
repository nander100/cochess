"""Tendency math (SPEC_V2 §9.2), checked against hand-computed values."""

from datetime import UTC, datetime, timedelta

import pytest

from app.analysis.detectors.types import Severity, ThemeName
from app.analysis.evals import Color
from app.analysis.tendencies import FactRecord, GameFacts, aggregate, trend, weigh
from app.config import TendencySettings

DAY0 = datetime(2026, 1, 1, tzinfo=UTC)
# Half-life 1 game: weights 1, 0.5, 0.25, ... so the sums are easy to check by hand.
HALVING = TendencySettings(half_life_games=1)


def fact(theme: ThemeName, severity: Severity, ply: int | None = 20) -> FactRecord:
    move_number = None if ply is None else (ply + 1) // 2
    san = None if ply is None else f"N{ply}"  # a stand-in SAN that names the ply
    return FactRecord(
        theme=theme, severity=severity, ply=ply, move_number=move_number, move_san=san
    )


def game(
    game_id: str,
    days_ago: int,
    facts: list[FactRecord] | None = None,
    color: Color = "white",
    accuracy: float | None = 80,
    opening: float | None = None,
) -> GameFacts:
    return GameFacts(
        game_id=game_id,
        played_at=DAY0 - timedelta(days=days_ago),
        user_color=color,
        accuracy=accuracy,
        phase_accuracy={"opening": opening, "middlegame": None, "endgame": None},
        facts=facts or [],
    )


def three_games() -> list[GameFacts]:
    note = fact("pawn_structure", "note", ply=None)  # always-on summary: never counts
    return [
        # Out of date order on purpose: g2 is the oldest.
        game("g2", 2, [fact("hung_piece", "inaccuracy", 30), note], accuracy=None, opening=50),
        game(
            "g0",
            0,
            [
                fact("hung_piece", "mistake", 15),
                fact("hung_piece", "blunder", 21),
                fact("king_safety", "inaccuracy", 9),
                fact("king_safety", "inaccuracy", 11),
                fact("king_safety", "inaccuracy", 13),
                note,
            ],
            opening=90,
        ),
        game(
            "g1",
            1,
            [fact("time_trouble", "concern", ply=None), note],
            color="black",
            accuracy=60,
            opening=70,
        ),
    ]


def test_weights_halve_every_half_life() -> None:
    games = [game(f"g{age:02}", age) for age in range(21)]

    weighted = weigh(games, TendencySettings())

    assert [g.age for g in weighted[:3]] == [0, 1, 2]
    assert weighted[0].weight == 1
    assert weighted[10].weight == pytest.approx(0.5)
    assert weighted[20].weight == pytest.approx(0.25)


def test_games_are_ordered_by_date_played() -> None:
    weighted = weigh(three_games(), HALVING)

    assert [(g.game.game_id, g.weight) for g in weighted] == [("g0", 1), ("g1", 0.5), ("g2", 0.25)]


def test_rates_and_scores() -> None:
    report = aggregate(three_games(), HALVING)

    by_theme = {t.theme: t for t in report.tendencies}
    # Σw = 1 + 0.5 + 0.25 = 1.75.
    # hung_piece: counts 2, 0, 1 → (1*2 + 0.25*1) / 1.75 = 1.2857.
    #   severity: mistake 2 + blunder 3 = 5, then inaccuracy 1 → (5 + 0.25) / 1.75 = 3.0.
    assert by_theme["hung_piece"].rate_per_game == 1.29
    assert by_theme["hung_piece"].score == 3.0
    assert by_theme["hung_piece"].games_seen == 2
    # king_safety: 3 inaccuracies in g0 → 3 / 1.75 = 1.714 for both.
    assert by_theme["king_safety"].rate_per_game == 1.71
    assert by_theme["king_safety"].score == 1.71
    # time_trouble (game-level concern, weight 2) in g1: 0.5 / 1.75 = 0.2857, 1 / 1.75 = 0.5714.
    assert by_theme["time_trouble"].rate_per_game == 0.29
    assert by_theme["time_trouble"].score == 0.57


def test_ranked_by_severity_weighted_score_not_rate() -> None:
    report = aggregate(three_games(), HALVING)

    # king_safety happens more often, but hung_piece's blunder and mistake make it rank first.
    assert [t.theme for t in report.tendencies] == ["hung_piece", "king_safety", "time_trouble"]


def test_game_level_notes_never_count() -> None:
    report = aggregate(three_games(), HALVING)

    assert "pawn_structure" not in {t.theme for t in report.tendencies}


def test_game_level_theme_counts_once_per_game() -> None:
    games = [game("g0", 0, [fact("slow_development", "concern", None)] * 2)]

    (tendency,) = aggregate(games, HALVING).tendencies

    assert (tendency.rate_per_game, tendency.score) == (1.0, 2.0)
    assert (tendency.recent_example.move_number, tendency.recent_example.move_san) == (None, None)


def test_recent_example_is_the_worst_fact_in_the_latest_game() -> None:
    report = aggregate(three_games(), HALVING)

    hung = next(t for t in report.tendencies if t.theme == "hung_piece")
    assert hung.recent_example.model_dump() == {
        "game_id": "g0",
        "move_number": 11,
        "move_san": "N21",
    }


def test_provisional_until_five_games() -> None:
    four = [game(f"g{i}", i, [fact("hung_piece", "mistake")]) for i in range(4)]
    five = [*four, game("g4", 4)]

    assert aggregate(four, HALVING).provisional is True
    assert aggregate(four, HALVING).tendencies[0].provisional is True
    assert aggregate(five, HALVING).provisional is False
    assert aggregate(five, HALVING).tendencies[0].provisional is False


def _trend(counts: list[int]) -> str | None:
    settings = TendencySettings()
    weighted = weigh([game(f"g{age:02}", age) for age in range(len(counts))], settings)
    return trend(weighted, counts, settings)


def test_trend_needs_ten_games() -> None:
    assert _trend([1] * 9) is None


def test_trend_compares_the_last_five_games_with_the_five_before() -> None:
    assert _trend([1, 1, 1, 1, 1, 0, 0, 0, 0, 0]) == "worsening"
    assert _trend([0, 0, 0, 0, 0, 1, 1, 1, 1, 1]) == "improving"
    # Ages 0-4 weigh 1 + 0.933 + 0.871 + 0.812 + 0.758 = 4.374: one occurrence at age 0 is
    # 1 / 4.374 = 0.229 per game, inside the 0.25 margin; two are 0.457, outside it.
    assert _trend([1, 0, 0, 0, 0, 0, 0, 0, 0, 0]) == "steady"
    assert _trend([2, 0, 0, 0, 0, 0, 0, 0, 0, 0]) == "worsening"
    # Games beyond the first ten don't affect the trend.
    assert _trend([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 9, 9]) == "steady"


def test_accuracy_is_weighted_and_skips_games_without_one() -> None:
    accuracy = aggregate(three_games(), HALVING).accuracy

    # Overall: g0 80 (w 1), g1 60 (w 0.5), g2 none → (80 + 30) / 1.5 = 73.33.
    assert accuracy.overall == 73.3
    assert accuracy.by_color == {"white": 80.0, "black": 60.0}
    # Opening: 90, 70, 50 → (90 + 35 + 12.5) / 1.75 = 78.57.
    assert accuracy.by_phase == {"opening": 78.6, "middlegame": None, "endgame": None}


def test_no_games() -> None:
    report = aggregate([], HALVING)

    assert report.games_analyzed == 0
    assert report.tendencies == []
    assert report.accuracy.overall is None
