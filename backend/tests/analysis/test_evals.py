import chess
import pytest
from pydantic import ValidationError

from app.analysis.evals import (
    Evaluation,
    for_color,
    format_eval,
    terminal_evaluation,
    win_percent,
    winning_chances,
)


@pytest.mark.parametrize(
    ("cp", "expected"),
    [(0, 0.0), (100, 0.182052), (-100, -0.182052), (300, 0.502251), (1000, 0.950895)],
)
def test_winning_chances_match_lichess_formula(cp: int, expected: float) -> None:
    assert winning_chances(Evaluation(cp=cp)) == pytest.approx(expected, abs=1e-6)


def test_centipawns_are_clamped_at_1000_like_lichess() -> None:
    assert winning_chances(Evaluation(cp=5000)) == winning_chances(Evaluation(cp=1000))
    assert winning_chances(Evaluation(cp=-5000)) == winning_chances(Evaluation(cp=-1000))


def test_mate_scores_map_to_plus_minus_one() -> None:
    assert winning_chances(Evaluation(mate=3)) == 1.0
    assert winning_chances(Evaluation(mate=-1)) == -1.0


def test_checkmate_maps_to_the_winner() -> None:
    assert winning_chances(Evaluation(checkmated="black")) == 1.0
    assert winning_chances(Evaluation(checkmated="white")) == -1.0


def test_win_percent_matches_lichess_ceiling_value() -> None:
    assert win_percent(Evaluation(cp=1000)) == pytest.approx(97.5447, abs=1e-4)


def test_for_color_flips_only_for_black() -> None:
    assert for_color(0.25, "white") == 0.25
    assert for_color(0.25, "black") == -0.25


@pytest.mark.parametrize(
    ("evaluation", "text"),
    [
        (Evaluation(cp=34), "+0.3"),
        (Evaluation(cp=-200), "-2.0"),
        (Evaluation(cp=-4), "0.0"),
        (Evaluation(cp=0), "0.0"),
        (Evaluation(cp=1550), "+15.5"),
        (Evaluation(mate=3), "+M3"),
        (Evaluation(mate=-2), "-M2"),
        (Evaluation(checkmated="black"), "+M0"),
        (Evaluation(checkmated="white"), "-M0"),
    ],
)
def test_format_eval(evaluation: Evaluation, text: str) -> None:
    assert format_eval(evaluation) == text


@pytest.mark.parametrize(
    "fields",
    [{}, {"cp": 10, "mate": 2}, {"mate": 0}, {"cp": 0, "checkmated": "white"}],
    ids=["none", "cp-and-mate", "mate-zero", "cp-and-checkmated"],
)
def test_evaluation_requires_exactly_one_valid_form(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Evaluation.model_validate(fields)


def test_terminal_evaluation_of_checkmate_names_the_mated_side() -> None:
    board = chess.Board()
    for san in ["f3", "e5", "g4", "Qh4#"]:
        board.push_san(san)

    assert terminal_evaluation(board) == Evaluation(checkmated="white")


def test_terminal_evaluation_of_stalemate_is_a_draw() -> None:
    board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")

    assert terminal_evaluation(board) == Evaluation(cp=0)


def test_non_terminal_position_has_no_terminal_evaluation() -> None:
    assert terminal_evaluation(chess.Board()) is None
