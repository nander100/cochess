import chess
import pytest

from app.analysis.engine import EngineResult
from app.analysis.evals import Evaluation
from app.analysis.pgn import parse_pgn
from app.coach.tools import ToolInputError, build_tool_result, parse_tool_input
from app.config import Thresholds
from tests.engine_fakes import fake_result
from tests.pgn_fixtures import read_pgn

OPERA = parse_pgn(read_pgn("opera_game.pgn"), max_chars=100_000, max_plies=600)
FOOLS_MATE_SETUP = parse_pgn("1. f3 e5 2. g4 *", max_chars=1000, max_plies=10)


def deep(fen: str, cp: int) -> EngineResult:
    return EngineResult.model_validate(fake_result(fen, "deep", cp=cp, lines=4, plies=10))


class TestParseToolInput:
    def test_position_only(self) -> None:
        request = parse_tool_input({"ply": 9}, OPERA)

        assert (request.ply, request.fen) == (9, OPERA.positions[8].fen_before)
        assert [p.label for p in request.positions()] == ["position"]

    def test_candidate_move_is_checked_and_its_position_added(self) -> None:
        request = parse_tool_input({"ply": 9, "candidate_move_san": " gxf3 "}, OPERA)

        assert request.candidate_san == "gxf3"
        board = chess.Board(OPERA.positions[8].fen_before)
        board.push_san("gxf3")
        assert [(p.label, p.fen) for p in request.positions()] == [
            ("position", OPERA.positions[8].fen_before),
            ("after_candidate", board.fen()),
        ]

    def test_candidate_is_normalized_to_proper_san(self) -> None:
        request = parse_tool_input({"ply": 1, "candidate_move_san": "Ng1f3"}, OPERA)

        assert request.candidate_san == "Nf3"

    def test_illegal_candidate_is_explained(self) -> None:
        with pytest.raises(ToolInputError, match=r"Nxe5 is not a legal move in that position"):
            parse_tool_input({"ply": 9, "candidate_move_san": "Nxe5"}, OPERA)

    @pytest.mark.parametrize("ply", [0, 35, -1, "9", True, None])
    def test_ply_must_be_inside_the_game(self, ply: object) -> None:
        with pytest.raises(ToolInputError, match="from 1 to 34"):
            parse_tool_input({"ply": ply}, OPERA)

    def test_the_final_position_after_mate_cannot_be_analyzed(self) -> None:
        with pytest.raises(ToolInputError, match="already over"):
            parse_tool_input({"ply": 34}, OPERA)

    def test_a_mating_candidate_is_scored_from_the_board(self) -> None:
        request = parse_tool_input({"ply": 4, "candidate_move_san": "Qh4#"}, FOOLS_MATE_SETUP)

        assert request.after_candidate_fen is None
        assert request.after_candidate_terminal == Evaluation(checkmated="white")
        assert len(request.positions()) == 1

    def test_input_must_be_an_object(self) -> None:
        with pytest.raises(ToolInputError):
            parse_tool_input(["ply", 9], OPERA)


class TestBuildToolResult:
    def test_compares_the_candidate_with_the_best_move(self) -> None:
        request = parse_tool_input({"ply": 9, "candidate_move_san": "gxf3"}, OPERA)
        [position, after] = request.positions()
        results = {position.fen: deep(position.fen, 80), after.fen: deep(after.fen, -150)}

        result = build_tool_result(request, OPERA, results, Thresholds())

        assert (result.ply, result.move_number, result.side_to_move) == (9, 5, "white")
        assert result.played_in_game == "Qxf3"
        assert result.moves_before.endswith("4. dxe5 Bxf3")
        assert (result.eval, len(result.best_lines), result.depth) == ("+0.8", 4, 20)
        assert result.candidate is not None
        assert (result.candidate.move_san, result.candidate.eval_after) == ("gxf3", "-1.5")
        assert result.candidate.classification_if_played == "blunder"
        assert result.candidate.is_best_move is False
        assert len(result.candidate.best_replies) == 4

    def test_a_mating_candidate_has_no_replies(self) -> None:
        request = parse_tool_input({"ply": 4, "candidate_move_san": "Qh4#"}, FOOLS_MATE_SETUP)
        fen = request.positions()[0].fen

        result = build_tool_result(request, FOOLS_MATE_SETUP, {fen: deep(fen, 0)}, Thresholds())

        assert result.candidate is not None
        assert (result.candidate.eval_after, result.candidate.best_replies) == ("-M0", [])
        assert result.candidate.classification_if_played is None  # mating is never worse
