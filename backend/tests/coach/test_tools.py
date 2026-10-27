import chess
import pytest

from app.analysis.engine import EngineResult
from app.analysis.evals import Evaluation
from app.analysis.paths import resolve_path
from app.analysis.pgn import parse_pgn
from app.coach.tools import ToolInputError, build_tool_result, parse_tool_input
from app.config import Thresholds
from tests.engine_fakes import fake_result
from tests.pgn_fixtures import read_pgn

OPERA = parse_pgn(read_pgn("opera_game.pgn"), max_chars=100_000, max_plies=600)
FOOLS_MATE_SETUP = parse_pgn("1. f3 e5 2. g4 *", max_chars=1000, max_plies=10)
# The player's board: after 2. Nf3 in the Opera game, and in a line of their own (2...Nc6 3. Bb5).
ON_GAME = resolve_path(OPERA, ["e2e4", "e7e5", "g1f3"], max_plies=600)
IN_LINE = resolve_path(OPERA, ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"], max_plies=600)


def deep(fen: str, cp: int) -> EngineResult:
    return EngineResult.model_validate(fake_result(fen, "deep", cp=cp, lines=4, plies=10))


class TestParseToolInput:
    def test_a_game_position(self) -> None:
        request = parse_tool_input({"ply": 9}, OPERA, ON_GAME)

        assert (request.ply, request.fen) == (9, OPERA.positions[8].fen_before)
        assert request.played_in_game == "Qxf3"
        assert [p.label for p in request.positions()] == ["position"]

    def test_without_a_ply_the_board_position_on_the_game(self) -> None:
        request = parse_tool_input({}, OPERA, ON_GAME)

        assert (request.fen, request.ply) == (ON_GAME.fen, 4)
        assert request.moves_before == "1. e4 e5 2. Nf3"
        assert request.played_in_game == "d6"  # the game continued 2...d6

    def test_without_a_ply_the_board_position_in_the_players_line(self) -> None:
        request = parse_tool_input({"candidate_moves_san": ["a6"]}, OPERA, IN_LINE)

        assert (request.fen, request.ply, request.played_in_game) == (IN_LINE.fen, None, None)
        assert request.moves_before == "1. e4 e5 2. Nf3 Nc6 3. Bb5"
        assert request.candidate_sans == ("a6",)

    def test_a_sequence_of_moves_is_checked_in_order(self) -> None:
        request = parse_tool_input(
            {"ply": 9, "candidate_moves_san": [" gxf3 ", "Qd7", "Bh3"]}, OPERA, ON_GAME
        )

        assert request.candidate_sans == ("gxf3", "Qd7", "Bh3")
        board = chess.Board(OPERA.positions[8].fen_before)
        for san in ("gxf3", "Qd7", "Bh3"):
            board.push_san(san)
        assert [(p.label, p.fen) for p in request.positions()] == [
            ("position", OPERA.positions[8].fen_before),
            ("after_candidate", board.fen()),
        ]

    def test_moves_are_normalized_to_proper_san(self) -> None:
        request = parse_tool_input({"ply": 1, "candidate_moves_san": ["Ng1f3"]}, OPERA, ON_GAME)

        assert request.candidate_sans == ("Nf3",)

    def test_an_illegal_first_move_is_explained(self) -> None:
        with pytest.raises(ToolInputError, match=r"Nxe5 is not a legal move in that position"):
            parse_tool_input({"ply": 9, "candidate_moves_san": ["Nxe5"]}, OPERA, ON_GAME)

    def test_an_illegal_later_move_names_what_came_before(self) -> None:
        with pytest.raises(
            ToolInputError, match=r"Bb5 is not a legal move after gxf3 \(Black to move\)"
        ):
            parse_tool_input({"ply": 9, "candidate_moves_san": ["gxf3", "Bb5"]}, OPERA, ON_GAME)

    def test_at_most_three_moves(self) -> None:
        with pytest.raises(ToolInputError, match="At most 3"):
            parse_tool_input({"candidate_moves_san": ["d6", "d4", "Bg4", "dxe5"]}, OPERA, ON_GAME)

    def test_v1s_single_candidate_field_still_works(self) -> None:
        request = parse_tool_input({"ply": 9, "candidate_move_san": "gxf3"}, OPERA, ON_GAME)

        assert request.candidate_sans == ("gxf3",)

    @pytest.mark.parametrize("ply", [0, 35, -1, "9", True])
    def test_ply_must_be_inside_the_game(self, ply: object) -> None:
        with pytest.raises(ToolInputError, match="from 1 to 34"):
            parse_tool_input({"ply": ply}, OPERA, ON_GAME)

    def test_candidates_must_be_a_list_of_moves(self) -> None:
        with pytest.raises(ToolInputError, match="list of moves"):
            parse_tool_input({"candidate_moves_san": "Nf3"}, OPERA, ON_GAME)

    def test_the_final_position_after_mate_cannot_be_analyzed(self) -> None:
        with pytest.raises(ToolInputError, match="already over"):
            parse_tool_input({"ply": 34}, OPERA, ON_GAME)

    def test_a_mating_candidate_is_scored_from_the_board(self) -> None:
        board = resolve_path(FOOLS_MATE_SETUP, ["f2f3", "e7e5", "g2g4"], max_plies=10)

        request = parse_tool_input({"candidate_moves_san": ["Qh4#"]}, FOOLS_MATE_SETUP, board)

        assert request.after_candidate_fen is None
        assert request.after_candidate_terminal == Evaluation(checkmated="white")
        assert len(request.positions()) == 1

    def test_moves_after_mate_are_refused(self) -> None:
        board = resolve_path(FOOLS_MATE_SETUP, ["f2f3", "e7e5", "g2g4"], max_plies=10)

        with pytest.raises(ToolInputError, match="over before Kf2"):
            parse_tool_input({"candidate_moves_san": ["Qh4#", "Kf2"]}, FOOLS_MATE_SETUP, board)

    def test_input_must_be_an_object(self) -> None:
        with pytest.raises(ToolInputError):
            parse_tool_input(["ply", 9], OPERA, ON_GAME)


class TestBuildToolResult:
    def test_compares_the_candidate_with_the_best_move(self) -> None:
        request = parse_tool_input({"ply": 9, "candidate_moves_san": ["gxf3"]}, OPERA, ON_GAME)
        [position, after] = request.positions()
        results = {position.fen: deep(position.fen, 80), after.fen: deep(after.fen, -150)}

        result = build_tool_result(request, results, Thresholds())

        assert (result.ply, result.move_number, result.side_to_move) == (9, 5, "white")
        assert result.played_in_game == "Qxf3"
        assert result.moves_before.endswith("4. dxe5 Bxf3")
        assert (result.eval, len(result.best_lines), result.depth) == ("+0.8", 4, 20)
        assert result.candidate is not None
        assert (result.candidate.moves_san, result.candidate.eval_after) == (["gxf3"], "-1.5")
        assert result.candidate.classification_if_played == "blunder"
        assert result.candidate.is_best_move is False
        assert len(result.candidate.best_replies) == 4

    def test_a_variation_position_has_no_game_ply(self) -> None:
        request = parse_tool_input({}, OPERA, IN_LINE)

        result = build_tool_result(request, {IN_LINE.fen: deep(IN_LINE.fen, 20)}, Thresholds())

        assert (result.ply, result.move_number, result.side_to_move) == (None, 3, "black")
        assert result.played_in_game is None and result.candidate is None

    def test_a_mating_candidate_has_no_replies(self) -> None:
        board = resolve_path(FOOLS_MATE_SETUP, ["f2f3", "e7e5", "g2g4"], max_plies=10)
        request = parse_tool_input({"candidate_moves_san": ["Qh4#"]}, FOOLS_MATE_SETUP, board)

        result = build_tool_result(request, {board.fen: deep(board.fen, 0)}, Thresholds())

        assert result.candidate is not None
        assert (result.candidate.eval_after, result.candidate.best_replies) == ("-M0", [])
        assert result.candidate.classification_if_played is None  # mating is never worse
