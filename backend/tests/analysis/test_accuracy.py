import pytest

from app.analysis.accuracy import MoveAccuracy, aggregate, move_accuracies, move_accuracy


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [(60, 50, 64.5798), (60, 55, 80.8153), (70, 50, 41.0168), (90, 40, 9.5278), (100, 0, 0.0)],
)
def test_move_accuracy_matches_lichess_formula(
    before: float, after: float, expected: float
) -> None:
    assert move_accuracy(before, after) == pytest.approx(expected, abs=1e-3)


def test_holding_or_improving_win_percent_is_perfect() -> None:
    assert move_accuracy(50, 50) == 100
    assert move_accuracy(50, 70) == 100


def test_per_move_accuracy_uses_the_movers_point_of_view() -> None:
    moves = move_accuracies([50, 40, 50])  # White loses 10 points, then Black does

    assert [(m.ply, m.color) for m in moves] == [(1, "white"), (2, "black")]
    assert [round(m.accuracy, 2) for m in moves] == [64.58, 64.58]


def test_flat_games_get_the_minimum_weight() -> None:
    assert {m.weight for m in move_accuracies([50.0] * 30)} == {0.5}


def test_short_games_still_get_one_weight_per_move() -> None:
    assert len(move_accuracies([50, 55])) == 1


def test_aggregate_of_equal_moves_is_that_value() -> None:
    moves = [MoveAccuracy(ply, "white", 80.0, w) for ply, w in [(1, 0.5), (3, 4.0)]]

    assert aggregate(moves) == pytest.approx(80.0)


def test_aggregate_mixes_weighted_and_harmonic_means() -> None:
    moves = [MoveAccuracy(1, "white", 100.0, 1.0), MoveAccuracy(3, "white", 50.0, 1.0)]

    # weighted mean 75, harmonic mean 66.67
    assert aggregate(moves) == pytest.approx((75 + 200 / 3) / 2)


def test_a_zero_accuracy_move_zeroes_the_harmonic_mean() -> None:
    moves = [MoveAccuracy(1, "white", 100.0, 1.0), MoveAccuracy(3, "white", 0.0, 1.0)]

    assert aggregate(moves) == pytest.approx(25.0)


def test_aggregate_of_nothing_is_none() -> None:
    assert aggregate([]) is None
