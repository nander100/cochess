"""The dashboard's aggregation (SPEC_V3 §8.1), on hand-made rows: pure, no database."""

from datetime import UTC, datetime, timedelta

from app.analysis.dashboard import Dashboard, GameRow, OnboardingCard, Range, Snapshot, build
from app.analysis.tendencies import AccuracyReport, Example, Tendency, TendencyReport
from app.config import PuzzleSettings

START = datetime(2026, 10, 1, tzinfo=UTC)
CARD = OnboardingCard(complete=False, analyzed=3, total=12, has_report=False)


def row(n: int, accuracy: float | None, *, done: int = 0, total: int = 0) -> GameRow:
    return GameRow(
        game_id=f"g{n}", played_at=START + timedelta(days=n), opponent=f"Rival {n}",
        color="white" if n % 2 else "black", result="win", accuracy=accuracy,
        accuracy_opening=80.0, accuracy_middlegame=accuracy, accuracy_endgame=None,
        moments_total=total, moments_done=done,
    )  # fmt: skip


def tendency(theme: str, score: float, provisional: bool = False, game: str = "g3") -> Tendency:
    return Tendency.model_validate(
        {
            "theme": theme, "label": theme.replace("_", " "), "rate_per_game": score / 2,
            "score": score, "trend": "improving", "games_seen": 4, "provisional": provisional,
            "recent_example": Example(game_id=game, move_number=14, move_san="Nd4"),
        }
    )  # fmt: skip


def report(*tendencies: Tendency, games: int = 12) -> TendencyReport:
    accuracy = AccuracyReport(overall=None, by_color={}, by_phase={})
    return TendencyReport(
        games_analyzed=games, provisional=False, tendencies=list(tendencies), accuracy=accuracy
    )


LATEST = report(
    tendency("hung_piece", 3.0),
    tendency("time_trouble", 2.5, provisional=True),
    tendency("missed_tactic", 2.0),
    tendency("king_safety", 1.5),
    tendency("slow_development", 1.0),
    tendency("pawn_structure", 0.5),
)


def make(
    games: list[GameRow], latest: TendencyReport | None = LATEST, game_range: Range = "all"
) -> Dashboard:
    snapshots = [Snapshot(11, START, report(tendency("hung_piece", 4.0), games=11))]
    if latest is not None:
        snapshots.append(Snapshot(12, START + timedelta(days=1), latest))
    return build(games, latest, snapshots, CARD, {"g3": "black"}, PuzzleSettings(), game_range)


def test_focus_areas_are_the_top_three_settled_tendencies_with_puzzles_and_an_example() -> None:
    dashboard = make([row(1, 70)])

    assert [f.theme for f in dashboard.focus_areas] == [
        "hung_piece",
        "missed_tactic",
        "king_safety",
    ]
    first = dashboard.focus_areas[0]
    assert (first.example_game_id, first.example_move, first.example_ply) == ("g3", "14...Nd4", 28)
    assert [p.url for p in first.puzzles] == ["https://lichess.org/training/hangingPiece"]
    assert [p.theme for p in dashboard.focus_areas[2].puzzles] == [
        "kingsideAttack",
        "defensiveMove",
    ]


def test_the_mistake_chart_follows_the_top_five_themes_through_the_snapshots() -> None:
    trend = make([row(1, 70)]).mistake_trend

    assert [t.theme for t in trend.themes] == [
        "hung_piece", "time_trouble", "missed_tactic", "king_safety", "slow_development"
    ]  # fmt: skip
    assert [p.games_analyzed for p in trend.points] == [11, 12]
    assert trend.points[0].rates == {"hung_piece": 2.0}
    assert "pawn_structure" not in trend.points[1].rates


def test_accuracy_has_a_rolling_average_of_ten_and_phase_averages() -> None:
    games = [row(n, float(n), total=0) for n in range(12, 0, -1)]  # most recent first
    trend = make(games).accuracy

    assert [p.game_id for p in trend.points][:2] == ["g1", "g2"]  # oldest first
    assert trend.points[0].rolling == 1.0
    assert trend.points[-1].rolling == 7.5  # games 3 to 12
    assert trend.by_phase == {"opening": 80.0, "middlegame": 6.5, "endgame": None}


def test_games_without_accuracy_are_left_out_of_the_trend() -> None:
    assert [p.game_id for p in make([row(2, None), row(1, 60)]).accuracy.points] == ["g1"]


def test_continue_lists_games_with_unfinished_moments_and_recent_lists_ten() -> None:
    games = [row(n, 70, done=n % 3, total=2) for n in range(15, 0, -1)]
    dashboard = make(games)

    assert all(g.moments_done < g.moments_total for g in dashboard.continue_games)
    assert len(dashboard.continue_games) == 5
    assert [g.game_id for g in dashboard.recent][:3] == ["g15", "g14", "g13"]
    assert len(dashboard.recent) == 10


def test_the_range_keeps_the_most_recent_games() -> None:
    games = [row(n, 70) for n in range(30, 0, -1)]

    assert make(games, game_range="10").games == 10
    assert make(games, game_range="25").games == 25
    assert make(games, game_range="all").games == 30


def test_a_new_player_gets_an_empty_dashboard() -> None:
    dashboard = make([], latest=None)

    assert dashboard.games == 0 and dashboard.focus_areas == [] and dashboard.recent == []
    assert dashboard.mistake_trend.themes == [] and dashboard.accuracy.points == []
    assert dashboard.onboarding == CARD
