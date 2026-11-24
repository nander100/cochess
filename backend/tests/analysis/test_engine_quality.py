"""The engine quality check (SPEC_V4 §8.1): faster settings must keep v3's verdicts."""

from app.analysis.summary_models import GameSummary, MoveLabel
from scripts.engine_quality import BASELINE, compare, main, summary_from


def _v3() -> GameSummary:
    summary, _ = summary_from("game5b", BASELINE / "game5b.json")
    return summary


def _relabel(summary: GameSummary, plies: list[int], label: MoveLabel | None) -> GameSummary:
    moves = [
        m.model_copy(update={"classification": label}) if m.ply in plies else m
        for m in summary.move_list
    ]
    return summary.model_copy(update={"move_list": moves})


def test_the_same_results_pass() -> None:
    v3 = _v3()

    quality = compare("game5b", v3, v3)

    assert quality.passed and quality.same_labels == 1.0 and quality.lost == []


def _plies(summary: GameSummary, label: str) -> list[int]:
    return [m.ply for m in summary.move_list if m.classification == label]


def test_a_lost_blunder_fails_even_when_almost_every_label_is_the_same() -> None:
    v3 = _v3()
    blunders = _plies(v3, "blunder")
    assert blunders, "the fixture game has a blunder to lose"

    quality = compare("game5b", v3, _relabel(v3, blunders[:1], "inaccuracy"))

    assert not quality.passed
    assert len(quality.lost_blunders) == 1


def test_a_lost_mistake_is_listed_but_within_v3s_own_variation_it_passes() -> None:
    v3 = _v3()
    mistakes = _plies(v3, "mistake")
    assert mistakes, "the fixture game has a mistake"

    quality = compare("game5b", v3, _relabel(v3, mistakes[:1], "inaccuracy"))

    assert quality.passed and len(quality.lost) == 1 and quality.lost_blunders == []


def test_a_blunder_seen_as_a_mistake_is_still_found() -> None:
    v3 = _v3()

    assert compare("game5b", v3, _relabel(v3, _plies(v3, "blunder")[:1], "mistake")).lost == []


def test_the_bar_is_v3s_own_rerun_agreement_minus_a_point() -> None:
    v3 = _v3()

    assert round(compare("game5b", v3, v3).bar, 3) == 0.936
    assert round(compare("game3w", v3, v3).bar, 3) == 0.951


def test_too_many_changed_labels_fail() -> None:
    v3 = _v3()
    quiet = [m.ply for m in v3.move_list if m.classification is None]
    changed = quiet[: max(1, len(v3.move_list) // 10)]  # 10% of the moves

    quality = compare("game5b", v3, _relabel(v3, changed, "inaccuracy"))

    assert quality.lost == [] and quality.same_labels < quality.bar and not quality.passed


def test_the_command_passes_on_the_stored_captures() -> None:
    assert main(["game2b", "game5b"]) == 0
