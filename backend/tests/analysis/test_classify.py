import pytest

from app.analysis.classify import classify, is_missed_mate
from app.analysis.evals import Evaluation
from app.config import Thresholds

THRESHOLDS = Thresholds()


@pytest.mark.parametrize(
    ("drop", "expected"),
    [
        (0.0, None), (0.099, None), (0.10, "inaccuracy"),
        (0.2, "mistake"), (0.3, "blunder"), (1.5, "blunder"),
    ],
)  # fmt: skip
def test_classification_thresholds(drop: float, expected: str | None) -> None:
    assert classify(drop, THRESHOLDS) == expected


def test_losing_a_forced_mate_is_a_missed_mate() -> None:
    assert is_missed_mate(Evaluation(mate=2), Evaluation(cp=150), "white", THRESHOLDS)
    assert is_missed_mate(Evaluation(mate=-3), Evaluation(cp=-100), "black", THRESHOLDS)


def test_a_longer_mate_is_not_a_missed_mate() -> None:
    assert not is_missed_mate(Evaluation(mate=2), Evaluation(mate=5), "white", THRESHOLDS)


def test_delivering_mate_is_not_a_missed_mate() -> None:
    assert not is_missed_mate(
        Evaluation(mate=1), Evaluation(checkmated="black"), "white", THRESHOLDS
    )


def test_the_opponents_mate_is_not_the_movers_missed_mate() -> None:
    assert not is_missed_mate(Evaluation(mate=-2), Evaluation(cp=0), "white", THRESHOLDS)


def test_missing_a_mate_while_still_completely_winning_does_not_count() -> None:
    # +9.0 is ~97% for White: the mate is gone but the game is still dead won.
    assert not is_missed_mate(Evaluation(mate=10), Evaluation(cp=900), "white", THRESHOLDS)
    assert not is_missed_mate(Evaluation(mate=-4), Evaluation(cp=-9170), "black", THRESHOLDS)


def test_the_win_percent_cutoff_comes_from_config() -> None:
    strict = Thresholds(missed_mate_max_win_pct_after=99)

    assert is_missed_mate(Evaluation(mate=10), Evaluation(cp=900), "white", strict)
