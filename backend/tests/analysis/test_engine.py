import re
from typing import Any

import chess
import pytest
from pydantic import ValidationError

from app.analysis.engine import (
    EngineLine,
    EngineResult,
    EngineResultError,
    best_by_fen,
    check_batch,
    position_evaluations,
    uci_line_to_san,
)
from app.analysis.evals import Evaluation
from app.analysis.pgn import parse_pgn
from app.config import EngineTier
from tests.engine_fakes import fake_result

START = chess.STARTING_FEN
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
LONE_KINGS = "8/8/8/8/8/8/8/K6k w - - 0 1"
VERIFY = EngineTier(multipv=4, min_time_ms=1, min_depth=1, hard_cap_ms=1, max_line_plies=10)
SCAN = EngineTier(multipv=1, min_time_ms=1, min_depth=1, hard_cap_ms=1, max_line_plies=1)


def result(fen: str = START, tier: str = "verify", **kwargs: Any) -> EngineResult:
    return EngineResult.model_validate(fake_result(fen, tier, **kwargs))


def check_verify(batch: list[EngineResult], expected: list[str]) -> list[EngineResult]:
    return check_batch(batch, tier="verify", tier_config=VERIFY, expected_fens=expected)


class TestSchema:
    @pytest.mark.parametrize(
        "scores",
        [{}, {"eval_cp": 10, "mate": 2}, {"mate": 0}],
        ids=["no-score", "both", "mate-zero"],
    )
    def test_line_needs_exactly_one_non_zero_score(self, scores: dict[str, int]) -> None:
        with pytest.raises(ValidationError):
            EngineLine.model_validate({"rank": 1, "moves_uci": ["e2e4"], **scores})

    def test_line_needs_at_least_one_move(self) -> None:
        with pytest.raises(ValidationError):
            EngineLine(rank=1, eval_cp=0, moves_uci=[])

    def test_lines_must_be_ranked_one_to_n(self) -> None:
        data = fake_result(START, "verify", lines=2)
        data["lines"][0]["rank"], data["lines"][1]["rank"] = 2, 1

        with pytest.raises(ValidationError):
            EngineResult.model_validate(data)

    def test_result_evaluation_is_the_top_line(self) -> None:
        assert result(mate=-3, cp=None).evaluation() == Evaluation(mate=-3)


class TestCheckBatch:
    def test_accepts_a_complete_batch_and_truncates_lines(self) -> None:
        batch = [result(START, plies=12), result(AFTER_E4, plies=12)]

        checked = check_verify(batch, [START, AFTER_E4])

        assert [len(r.lines[0].moves_uci) for r in checked] == [10, 10]

    def test_scan_lines_keep_only_the_best_move(self) -> None:
        checked = check_batch(
            [result(START, "scan")], tier="scan", tier_config=SCAN, expected_fens=[START]
        )

        assert len(checked[0].lines[0].moves_uci) == 1

    @pytest.mark.parametrize(
        ("batch_fens", "message"),
        [
            ([START], "Missing engine results for 1 position(s)."),
            ([START, AFTER_E4, LONE_KINGS], "1 result(s) are for positions not requested."),
            ([START, START, AFTER_E4], "Each position may only be submitted once."),
        ],
        ids=["missing", "unexpected", "duplicate"],
    )
    def test_batch_must_cover_exactly_the_requested_positions(
        self, batch_fens: list[str], message: str
    ) -> None:
        with pytest.raises(EngineResultError, match=re.escape(message)):
            check_verify([result(fen) for fen in batch_fens], [START, AFTER_E4])

    def test_rejects_wrong_tier(self) -> None:
        with pytest.raises(EngineResultError, match="Expected verify results, got scan"):
            check_verify([result(tier="scan")], [START])

    def test_rejects_too_many_lines(self) -> None:
        with pytest.raises(EngineResultError, match="At most 1 line"):
            check_batch(
                [result(tier="scan", lines=2)], tier="scan", tier_config=SCAN, expected_fens=[START]
            )

    @pytest.mark.parametrize(
        ("moves", "message"),
        [(["e2e4", "e2e4"], "illegal move: e2e4"), (["e2e9"], "invalid move: e2e9")],
        ids=["illegal", "malformed"],
    )
    def test_rejects_bad_moves_in_a_line(self, moves: list[str], message: str) -> None:
        bad = fake_result(START, "verify")
        bad["lines"][0]["moves_uci"] = moves

        with pytest.raises(EngineResultError, match=message):
            check_verify([EngineResult.model_validate(bad)], [START])


def test_uci_line_to_san_uses_the_position() -> None:
    assert uci_line_to_san(START, ["e2e4", "e7e5", "g1f3", "b8c6"]) == ["e4", "e5", "Nf3", "Nc6"]


def test_uci_line_to_san_handles_castling_and_promotion() -> None:
    line = uci_line_to_san("4k3/1P6/8/8/8/8/8/4K2R w K - 0 1", ["e1g1", "e8d7", "b7b8q"])

    assert line == ["O-O", "Kd7", "b8=Q"]


def test_best_by_fen_prefers_higher_tiers() -> None:
    scan, verify = result(START, "scan", cp=10), result(START, "verify", cp=40)

    assert best_by_fen([scan, verify])[START] == verify
    assert best_by_fen([verify, scan])[START] == verify


def test_position_evaluations_use_the_board_for_a_terminal_final_position() -> None:
    game = parse_pgn("1. f3 e5 2. g4 Qh4# 0-1", max_chars=1000, max_plies=10)
    by_fen = {p.fen_before: result(p.fen_before, cp=-50) for p in game.positions}

    evals = position_evaluations(game, by_fen)

    assert evals == [Evaluation(cp=-50)] * 4 + [Evaluation(checkmated="white")]
