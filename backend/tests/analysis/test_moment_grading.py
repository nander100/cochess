"""Grading an attempt, the moves the coach must not name, the detectors on an attempt, and hints
(SPEC_V2 §8.3, §8.4). Hand-built positions with chosen engine lines."""

import chess
import pytest

from app.analysis.detectors.types import ThemeFact
from app.analysis.engine import EngineLine, EngineResult
from app.analysis.moments import (
    build_hints,
    candidate_facts,
    good_first_moves,
    grade,
)
from app.config import MomentSettings, Settings, Thresholds

START = chess.STARTING_FEN
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
SETTINGS = Settings(_env_file=None)
THRESHOLDS, MOMENTS = Thresholds(), MomentSettings()


def result(fen: str, *lines: tuple[int | str, list[str]]) -> EngineResult:
    """Lines as (eval, moves): an int is centipawns (White POV), "M2" / "-M2" a mate."""
    built = []
    for rank, (value, moves) in enumerate(lines, start=1):
        if isinstance(value, str):
            built.append(EngineLine(rank=rank, mate=int(value.replace("M", "")), moves_uci=moves))
        else:
            built.append(EngineLine(rank=rank, eval_cp=value, moves_uci=moves))
    return EngineResult(fen=fen, tier="deep", depth=22, time_ms=3000, lines=built)


def after(board_fen: str, uci: str, cp: int) -> EngineResult:
    board = chess.Board(board_fen)
    board.push_uci(uci)
    reply = next(iter(board.legal_moves)).uci()
    return result(board.fen(), (cp, [reply]))


START_LINES = result(START, (30, ["e2e4"]), (25, ["d2d4"]), (20, ["g1f3"]), (-50, ["f2f3"]))


@pytest.mark.parametrize(
    ("uci", "cp_after", "expected"),
    [
        ("e2e4", -500, "best"),  # the engine's top move is best, whatever the search after says
        ("d2d4", 28, "best"),  # within 0.02 of the best
        ("g1f3", 0, "good"),  # 0.055 lost: below the inaccuracy threshold
        ("f2f3", -50, "inaccuracy"),  # 0.147 lost
        ("g2g4", -120, "mistake"),  # 0.273 lost
        ("g2g4", -300, "blunder"),  # 0.557 lost
    ],
)
def test_grades_for_white(uci: str, cp_after: int, expected: str) -> None:
    board = chess.Board(START)

    graded = grade(
        board,
        chess.Move.from_uci(uci),
        START_LINES,
        after(START, uci, cp_after),
        THRESHOLDS,
        MOMENTS,
    )

    assert graded.grade == expected


def test_grades_are_from_the_movers_point_of_view() -> None:
    board = chess.Board(AFTER_E4)
    before = result(AFTER_E4, (30, ["e7e5"]))

    good = grade(board, chess.Move.from_uci("c7c5"), before, after(AFTER_E4, "c7c5", 35),
                 THRESHOLDS, MOMENTS)  # fmt: skip
    bad = grade(board, chess.Move.from_uci("f7f6"), before, after(AFTER_E4, "f7f6", 200),
                THRESHOLDS, MOMENTS)  # fmt: skip

    assert (good.grade, bad.grade) == ("best", "mistake")  # +2.0 for White is bad for Black
    assert bad.drop == pytest.approx(0.2972, abs=1e-4)  # wc(200) - wc(30) = 0.3524 - 0.0552


def test_a_mating_move_is_best_without_a_search_after() -> None:
    fen = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
    before = result(fen, (-40, ["b8c6"]))  # even when the engine's top line is something else

    graded = grade(chess.Board(fen), chess.Move.from_uci("d8h4"), before, None, THRESHOLDS, MOMENTS)

    assert graded.grade == "best"


def test_a_move_that_doesnt_end_the_game_needs_the_search_after() -> None:
    with pytest.raises(ValueError, match="needs a search"):
        grade(
            chess.Board(START), chess.Move.from_uci("a2a3"), START_LINES, None, THRESHOLDS, MOMENTS
        )


def test_the_moves_the_coach_must_not_name_are_the_good_first_moves() -> None:
    assert good_first_moves(chess.Board(START), START_LINES, THRESHOLDS) == ["e4", "d4", "Nf3"]


def test_good_first_moves_for_black() -> None:
    before = result(AFTER_E4, (30, ["e7e5"]), (40, ["c7c5"]), (150, ["f7f6"]))

    assert good_first_moves(chess.Board(AFTER_E4), before, THRESHOLDS) == ["e5", "c5"]


# A white knight on c3 and a black queen on d8: Nd5 hangs the knight to Qxd5; Ne4 is safe.
HANGING = "3qk3/8/8/8/8/2N5/8/4K3 w - - 0 1"
HANGING_BEFORE = result(HANGING, (300, ["c3e4"]))


def test_the_detectors_run_on_an_attempt() -> None:
    board = chess.Board(HANGING)
    move = chess.Move.from_uci("c3d5")
    after_nd5 = board.copy()
    after_nd5.push(move)
    reply = result(after_nd5.fen(), (-900, ["d8d5", "e1e2"]))
    graded = grade(board, move, HANGING_BEFORE, reply, THRESHOLDS, MOMENTS)

    facts = candidate_facts(board, move, 41, HANGING_BEFORE, reply, graded, SETTINGS)

    assert graded.grade == "blunder"
    [hung] = [f for f in facts if f.theme == "hung_piece"]
    assert (hung.details["piece"], hung.details["square"], hung.details["lost_to"]) == (
        "knight",
        "d5",
        "Qxd5",
    )


def test_a_good_attempt_has_no_facts() -> None:
    board = chess.Board(HANGING)
    move = chess.Move.from_uci("c3e2")
    reply = after(HANGING, "c3e2", 290)
    graded = grade(board, move, HANGING_BEFORE, reply, THRESHOLDS, MOMENTS)

    assert graded.grade == "best"
    assert candidate_facts(board, move, 41, HANGING_BEFORE, reply, graded, SETTINGS) == []


def fact(theme: str, **details: object) -> ThemeFact:
    return ThemeFact.model_validate(
        {"theme": theme, "severity": "mistake", "ply": 41, "details": details}
    )


BEST = chess.Move.from_uci("c3e4")


def test_hints_describe_the_attempts_problem_then_the_best_moves_shape() -> None:
    facts = [fact("hung_piece", piece="knight", square="d5", lost_to="Qxd5", material_lost=3)]

    level1, level2 = build_hints(facts, ["Qxd5"], chess.Board(HANGING), BEST)

    assert level1.model_dump() == {
        "level": 1,
        "kind": "candidate_problem",
        "text_facts": {"theme": "hung_piece", "piece": "knight", "square": "d5", "lost_to": "Qxd5"},
    }
    assert level2.model_dump() == {
        "level": 2,
        "kind": "best_move_shape",
        "text_facts": {"piece_type": "knight", "is_capture": False, "is_check": False},
    }


def test_facts_that_name_the_best_move_are_never_hints() -> None:
    facts = [
        fact("missed_tactic", subtype="fork", best_move="Ne4", line=["Ne4"], forces_mate=False),
        fact("missed_capture_or_check", best_move="Ne4", kind="check", material_won=0),
        fact("endgame_technique", subtype="passive_king", king_square="e1", best_move="Ke2"),
    ]

    level1, level2 = build_hints(facts, ["Qxd5", "Ke2"], chess.Board(HANGING), BEST)

    # No safe fact: the hint falls back to the opponent's best reply to the attempt.
    assert level1.text_facts == {"theme": None, "opponent_best_reply": "Qxd5"}
    text = str([level1.model_dump(), level2.model_dump()])
    assert "Ne4" not in text and "e4" not in text and "Ke2" not in text


def test_allowed_tactic_hints_leave_out_the_line() -> None:
    facts = [fact("allowed_tactic", subtype="fork", reply_move="Nc2+", line=["Nc2+", "Kd1"],
                  material_lost=5, allows_mate=False)]  # fmt: skip

    level1, _ = build_hints(facts, ["Nc2+"], chess.Board(HANGING), BEST)

    assert level1.text_facts == {
        "theme": "allowed_tactic",
        "subtype": "fork",
        "reply_move": "Nc2+",
        "allows_mate": False,
    }


def test_a_capture_with_check_has_that_shape() -> None:
    # White's queen takes the queen on e2, giving check along the open e-file.
    board = chess.Board("4k3/8/8/8/8/8/4q3/3QK3 w - - 0 1")

    _, shape = build_hints([], [], board, chess.Move.from_uci("d1e2"))

    assert shape.text_facts == {"piece_type": "queen", "is_capture": True, "is_check": True}
