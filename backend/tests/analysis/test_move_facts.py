"""Per-step move facts (SPEC_V3 §7.2) on hand-built positions."""

import pytest

from app.analysis.evals import Evaluation
from app.analysis.move_facts import StepFacts, step_facts

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
CP0, CP30 = Evaluation(cp=0), Evaluation(cp=30)


def one(
    fen: str, uci: str, before: Evaluation | None = None, after: Evaluation | None = None
) -> StepFacts:
    [fact] = step_facts(fen, [uci], [before, after])
    return fact


def test_a_quiet_move_attacks_and_hangs_nothing() -> None:
    fact = one(START, "e2e4", CP0, CP30)
    assert (fact.index, fact.move_number, fact.side, fact.san, fact.piece) == (
        1, 1, "white", "e4", "pawn"
    )  # fmt: skip
    assert (fact.from_square, fact.to_square) == ("e2", "e4")
    assert fact.captured is None and not fact.check and not fact.checkmate
    assert fact.newly_attacked == [] and fact.left_hanging == []
    assert fact.material == 0
    assert (fact.eval_after, fact.eval_change) == ("+0.3", "+0.3")


def test_a_capture_names_what_it_took_and_changes_the_material() -> None:
    fen = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    fact = one(fen, "e4d5")
    assert (fact.san, fact.captured, fact.material) == ("exd5", "pawn", 1)


def test_en_passant_takes_a_pawn() -> None:
    fen = "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"
    assert one(fen, "e5f6").captured == "pawn"


def test_mate_is_check_and_checkmate() -> None:
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
    fact = one(fen, "h5f7")
    assert (fact.san, fact.captured, fact.check, fact.checkmate) == ("Qxf7#", "pawn", True, True)


def test_a_fork_newly_attacks_a_loose_piece() -> None:
    fen = "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1"
    fact = one(fen, "d5c7")
    assert fact.check
    assert fact.newly_attacked == ["rook on a8"]
    assert fact.left_hanging == []


def test_a_piece_moved_en_prise_is_left_hanging() -> None:
    fen = "4k3/8/8/3p4/8/8/8/4KB2 w - - 0 1"
    fact = one(fen, "f1c4")
    assert fact.left_hanging == ["bishop on c4"]
    assert fact.newly_attacked == ["pawn on d5"]


def test_a_defended_piece_is_not_newly_attacked() -> None:
    fen = "4k3/2p5/3p4/8/8/8/8/4KB2 w - - 0 1"  # the d6 pawn is defended by c7
    fact = one(fen, "f1b5")
    assert fact.newly_attacked == []


def test_a_line_numbers_its_steps_and_sides() -> None:
    facts = step_facts(START, ["e2e4", "e7e5", "g1f3"], [CP0, CP30, Evaluation(cp=20), None])
    assert [(f.index, f.move_number, f.side, f.san) for f in facts] == [
        (1, 1, "white", "e4"), (2, 1, "black", "e5"), (3, 2, "white", "Nf3")
    ]  # fmt: skip
    assert [f.eval_change for f in facts] == ["+0.3", "-0.1", None]


def test_mate_scores_have_no_change() -> None:
    fact = one(START, "e2e4", CP0, Evaluation(mate=5))
    assert (fact.eval_after, fact.eval_change) == ("+M5", None)


def test_bad_input_is_refused() -> None:
    with pytest.raises(ValueError, match="one evaluation per position"):
        step_facts(START, ["e2e4"], [CP0])
    with pytest.raises(ValueError, match="not legal"):
        step_facts(START, ["e2e5"], [CP0, CP0])
