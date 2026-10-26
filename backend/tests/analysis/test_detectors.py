"""Hand-built positions for every detector: at least one where it fires, one where it doesn't."""

import pytest

from app.analysis.detectors import (
    allowed_tactic,
    endgame_technique,
    hung_piece,
    king_safety,
    missed_capture_or_check,
    missed_tactic,
    pawn_structure,
    run_detectors,
    slow_development,
    time_trouble,
)
from app.analysis.detectors.types import DetailValue
from app.analysis.evals import Evaluation
from tests.detector_helpers import game_ctx, move_ctx


class TestHungPiece:
    AFTER_NC3_D5 = "rnbqkbnr/ppp1pppp/8/3p4/8/2N5/PPPPPPPP/R1BQKBNR w KQkq d6 0 2"

    def test_knight_left_en_prise_to_a_pawn(self) -> None:
        ctx = move_ctx(self.AFTER_NC3_D5, "Ne4", best_after=["dxe4"])

        [fact] = hung_piece.detect(ctx)

        assert fact.details == {
            "piece": "knight",
            "square": "e4",
            "lost_to": "dxe4",
            "material_lost": 3,
        }
        assert (fact.ply, fact.move_number, fact.move_san, fact.severity) == (
            3,
            2,
            "Ne4",
            "mistake",
        )

    def test_an_even_trade_is_not_a_hung_piece(self) -> None:
        after_e4_d5 = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2"

        assert hung_piece.detect(move_ctx(after_e4_d5, "exd5", best_after=["Qxd5"])) == []

    def test_a_safe_developing_move_is_not_a_hung_piece(self) -> None:
        assert hung_piece.detect(move_ctx(self.AFTER_NC3_D5, "Nf3", best_after=["e5"])) == []

    def test_only_inaccuracies_or_worse_are_examined(self) -> None:
        ctx = move_ctx(self.AFTER_NC3_D5, "Ne4", best_after=["dxe4"], classification=None)

        assert hung_piece.detect(ctx) == []


class TestAllowedTactic:
    # Owner's game5b, 31...Kg7?? walks into 32. Qe7+, checking the king and hitting the rook.
    BEFORE_KG7 = "3r1k2/7p/6pb/5p2/1Q1Pp1n1/1P2Pq2/P4P2/R3KR2 b - - 0 31"

    def test_walking_into_a_queen_fork(self) -> None:
        ctx = move_ctx(
            self.BEFORE_KG7, "Kg7", best_after=["Qe7+", "Kg8", "Qxd8+", "Bf8"],
            classification="blunder",
        )  # fmt: skip

        [fact] = allowed_tactic.detect(ctx)

        assert fact.details == {
            "subtype": "fork",
            "reply_move": "Qe7+",
            "line": ["Qe7+", "Kg8", "Qxd8+", "Bf8"],
            "material_lost": 5,
            "allows_mate": False,
        }

    def test_allowing_a_back_rank_mate(self) -> None:
        ctx = move_ctx(
            "r5k1/8/8/8/8/8/2P2PPP/6K1 w - - 0 1", "c3", best_after=["Ra1#"],
            classification="blunder",
        )  # fmt: skip

        [fact] = allowed_tactic.detect(ctx)

        assert (fact.details["subtype"], fact.details["allows_mate"]) == ("back_rank", True)

    def test_a_hung_piece_is_left_to_the_hung_piece_detector(self) -> None:
        after_nc3_d5 = "rnbqkbnr/ppp1pppp/8/3p4/8/2N5/PPPPPPPP/R1BQKBNR w KQkq d6 0 2"

        assert allowed_tactic.detect(move_ctx(after_nc3_d5, "Ne4", best_after=["dxe4"])) == []

    def test_a_quiet_reply_is_not_a_tactic(self) -> None:
        ctx = move_ctx("6k1/8/8/8/8/8/P4PPP/6K1 w - - 0 1", "a3", best_after=["Kf7"])

        assert allowed_tactic.detect(ctx) == []

    def test_inaccuracies_are_below_the_threshold(self) -> None:
        ctx = move_ctx(
            self.BEFORE_KG7, "Kg7", best_after=["Qe7+", "Kg8", "Qxd8+", "Bf8"],
            classification="inaccuracy",
        )  # fmt: skip

        assert allowed_tactic.detect(ctx) == []


class TestMissedCaptureOrCheck:
    QUEEN_ON_H4 = "rnb1kbnr/pppp1ppp/8/4p3/4P2q/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"

    def test_quiet_move_instead_of_winning_the_queen(self) -> None:
        ctx = move_ctx(self.QUEEN_ON_H4, "Nc3", best_before=["Nxh4"])

        [fact] = missed_capture_or_check.detect(ctx)

        assert fact.details == {"best_move": "Nxh4", "kind": "capture", "material_won": 9}

    def test_playing_a_capture_is_not_a_miss(self) -> None:
        ctx = move_ctx(self.QUEEN_ON_H4, "Nxe5", best_before=["Nxh4"])

        assert missed_capture_or_check.detect(ctx) == []

    def test_inaccuracies_are_below_the_threshold(self) -> None:
        ctx = move_ctx(self.QUEEN_ON_H4, "Nc3", best_before=["Nxh4"], classification="inaccuracy")

        assert missed_capture_or_check.detect(ctx) == []


def tactic_subtype(fen: str, played: str, line: list[str]) -> DetailValue:
    [fact] = missed_tactic.detect(move_ctx(fen, played, best_before=line))
    return fact.details["subtype"]


class TestMissedTactic:
    FORK = "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1"

    def test_knight_fork_of_king_and_rook(self) -> None:
        [fact] = missed_tactic.detect(
            move_ctx(self.FORK, "Ke2", best_before=["Nc7+", "Kd7", "Nxa8"])
        )

        assert fact.details == {
            "subtype": "fork",
            "best_move": "Nc7+",
            "line": ["Nc7+", "Kd7", "Nxa8"],
            "material_won": 5,
            "forces_mate": False,
        }

    def test_skewer_of_king_and_queen(self) -> None:
        fen = "8/1q6/8/3k4/8/8/8/3B3K w - - 0 1"

        assert tactic_subtype(fen, "Kg2", ["Bf3+", "Kc5", "Bxb7"]) == "skewer"

    def test_pin_against_the_king(self) -> None:
        fen = "4k3/7p/2n5/8/3P4/8/8/4KB2 w - - 0 1"

        assert tactic_subtype(fen, "Kd2", ["Bb5", "h6", "d5", "h5", "dxc6"]) == "pin"

    def test_discovered_attack_on_the_queen(self) -> None:
        fen = "6k1/4q2p/8/8/4B3/8/8/4R1K1 w - - 0 1"

        assert tactic_subtype(fen, "Kh1", ["Bxh7+", "Kxh7", "Rxe7+"]) == "discovered_attack"

    def test_back_rank_mate(self) -> None:
        ctx = move_ctx(
            "6k1/5ppp/8/8/8/8/8/3R2K1 w - - 0 1", "Kf1", best_before=["Rd8#"],
            classification=None, missed_mate=True,
            eval_before=Evaluation(mate=1), eval_after=Evaluation(cp=500),
        )  # fmt: skip

        [fact] = missed_tactic.detect(ctx)

        assert fact.details["subtype"] == "back_rank"
        assert fact.details["forces_mate"] is True
        assert fact.details["material_won"] is None

    def test_plain_material_win_is_a_combination(self) -> None:
        assert tactic_subtype("4k3/8/8/8/8/2n5/8/2R1K3 w - - 0 1", "Kd2", ["Rxc3"]) == "combination"

    def test_a_line_winning_less_than_two_points_is_not_a_tactic(self) -> None:
        ctx = move_ctx("4k3/8/8/8/8/8/P7/4K3 w - - 0 1", "Kd2", best_before=["a4"])

        assert missed_tactic.detect(ctx) == []

    def test_playing_the_best_move_is_not_a_miss(self) -> None:
        ctx = move_ctx(self.FORK, "Nc7+", best_before=["Nc7+", "Kd7", "Nxa8"])

        assert missed_tactic.detect(ctx) == []


class TestSlowDevelopment:
    PAWN_PUSHES = (
        "1. a3 a6 2. b3 b6 3. c3 c6 4. d3 d6 5. e3 e6 6. f3 f6 7. g3 g6 8. h3 h6 "
        "9. a4 a5 10. b4 axb4 *"
    )

    def test_all_minor_pieces_home_at_move_ten(self) -> None:
        [fact] = slow_development.detect(game_ctx(self.PAWN_PUSHES, "white"))

        assert fact.severity == "note"
        assert fact.ply is None
        assert fact.details["undeveloped"] == ["knight b1", "knight g1", "bishop c1", "bishop f1"]
        assert fact.details["castled"] is False

    def test_raised_to_concern_when_the_opening_cost_winning_chances(self) -> None:
        cps = [0] * 20 + [-200]  # White's winning chances fall ~0.35 by the end of the opening

        [fact] = slow_development.detect(game_ctx(self.PAWN_PUSHES, "white", cps))

        assert fact.severity == "concern"
        assert fact.details["opening_wc_lost"] == pytest.approx(0.35, abs=0.01)

    def test_developed_and_castled_early_is_fine(self) -> None:
        pgn = (
            "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. O-O Nf6 5. d3 d6 6. Nc3 O-O 7. Bg5 h6 "
            "8. Bh4 g5 9. Bg3 Bg4 10. h3 Bh5 *"
        )

        assert slow_development.detect(game_ctx(pgn, "white")) == []

    def test_not_castled_by_move_twelve_with_queens_on(self) -> None:
        pgn = (
            "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. Nc3 Nf6 5. d3 d6 6. Bg5 h6 7. Bh4 g5 "
            "8. Bg3 a6 9. a3 b5 10. Ba2 Bb7 11. h3 Qe7 12. Qd2 Qf8 *"
        )

        [fact] = slow_development.detect(game_ctx(pgn, "white"))

        assert fact.details["undeveloped"] == []
        assert fact.details["not_castled_by_move"] == 12

    def test_games_shorter_than_ten_moves_are_skipped(self) -> None:
        assert slow_development.detect(game_ctx("1. a3 a6 2. b3 b6 *", "white")) == []


class TestKingSafety:
    def test_pushing_a_pawn_in_front_of_the_castled_king(self) -> None:
        [fact] = king_safety.detect(move_ctx("6k1/8/8/8/8/8/5PPP/6K1 w - - 0 1", "g4"))

        assert fact.details == {"pawn_moved": "g4"}

    def test_reply_line_mates_the_king(self) -> None:
        fen = "r5k1/8/8/8/8/8/2P2PPP/6K1 w - - 0 1"
        ctx = move_ctx(fen, "c3", best_after=["Ra1#"], classification="blunder")

        [fact] = king_safety.detect(ctx)

        assert fact.details == {"check_sequence": ["Ra1#"]}

    def test_a_check_that_just_grabs_material_is_not_a_king_attack(self) -> None:
        ctx = move_ctx("q3k3/8/8/8/8/8/8/4K2R w K - 0 1", "Kd1", best_after=["Qxh1+"])

        assert king_safety.detect(ctx) == []

    def test_quiet_mistake_away_from_the_king(self) -> None:
        ctx = move_ctx("6k1/8/8/8/8/8/P4PPP/6K1 w - - 0 1", "a3", best_after=["Kf7"])

        assert king_safety.detect(ctx) == []

    def test_inaccuracies_are_below_the_threshold(self) -> None:
        ctx = move_ctx("6k1/8/8/8/8/8/5PPP/6K1 w - - 0 1", "g4", classification="inaccuracy")

        assert king_safety.detect(ctx) == []


class TestPawnStructure:
    DOUBLING = "4k3/8/8/8/8/4p3/4PP2/4K3 w - - 0 1"

    def test_capture_that_doubles_and_isolates_pawns(self) -> None:
        facts = pawn_structure.detect(move_ctx(self.DOUBLING, "fxe3", classification="inaccuracy"))

        assert [f.details for f in facts] == [
            {"weakness": "doubled", "files": ["e"]},
            {"weakness": "isolated", "files": ["e"]},
        ]

    def test_a_king_move_creates_no_weakness(self) -> None:
        ctx = move_ctx(self.DOUBLING, "Kd1", classification="inaccuracy")

        assert pawn_structure.detect(ctx) == []

    def test_game_summary_at_the_end_of_the_opening(self) -> None:
        game = game_ctx("1. d4 e5 2. dxe5 d6 3. exd6 cxd6 *", "black")

        [fact] = pawn_structure.detect_game(game)

        assert fact.severity == "note"
        assert fact.details == {
            "scope": "end_of_opening",
            "at_move": 3,
            "doubled_files": [],
            "isolated_pawns": 1,
            "isolated_files": ["d"],
            "passed_pawns": [],
        }


class TestEndgameTechnique:
    KP_VS_K = "8/8/8/4k3/8/8/4P3/4K3 w - - 0 1"

    def test_threw_away_a_winning_endgame(self) -> None:
        ctx = move_ctx(
            self.KP_VS_K, "Kd1", best_before=["e4"], classification="blunder",
            eval_before=Evaluation(cp=500), eval_after=Evaluation(cp=0),
        )  # fmt: skip

        [fact] = endgame_technique.detect(ctx)

        assert fact.details == {
            "subtype": "threw_win",
            "win_pct_before": 86.3,
            "win_pct_after": 50.0,
        }

    def test_passive_king_when_the_king_should_have_moved(self) -> None:
        ctx = move_ctx(
            self.KP_VS_K, "e3", best_before=["Kd2"],
            eval_before=Evaluation(cp=400), eval_after=Evaluation(cp=300),
        )  # fmt: skip

        [fact] = endgame_technique.detect(ctx)

        assert fact.details == {"subtype": "passive_king", "king_square": "e1", "best_move": "Kd2"}

    def test_capture_that_lets_the_opponent_get_a_passed_pawn(self) -> None:
        ctx = move_ctx("4k3/8/8/2p1p3/3P4/8/8/4K3 w - - 0 1", "dxc5", eval_after=Evaluation(cp=-50))

        [fact] = endgame_technique.detect(ctx)

        assert fact.details == {"subtype": "allowed_passer", "squares": ["e5"]}

    def test_not_in_the_endgame(self) -> None:
        start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

        assert endgame_technique.detect(move_ctx(start, "e4", classification="blunder")) == []


class TestTimeTrouble:
    PGN = (
        '[TimeControl "600"]\n\n'
        "1. e4 {[%clk 0:09:50]} e5 {[%clk 0:09:50]} 2. Nf3 {[%clk 0:00:50]} "
        "Nc6 {[%clk 0:09:00]} 3. Bc4 {[%clk 0:00:40]} *"
    )

    def test_blunder_made_under_ten_percent_of_the_base_time(self) -> None:
        cps = [0, 0, 0, -300, -300, -300]  # White's 2nd move (ply 3) blunders at 0:50

        [fact] = time_trouble.detect(game_ctx(self.PGN, "white", cps))

        assert fact.severity == "concern"
        assert fact.details == {
            "base_time_s": 600,
            "low_clock_threshold_s": 60.0,
            "low_clock_from_move": 2,
            "user_moves": 3,
            "moves_in_low_clock": 2,
            "mistakes_and_blunders": 1,
            "mistakes_and_blunders_in_low_clock": 1,
            "share_in_low_clock_pct": 100,
        }

    def test_without_a_time_control_low_clock_is_30_seconds(self) -> None:
        pgn = self.PGN.replace('[TimeControl "600"]\n\n', "")

        [fact] = time_trouble.detect(game_ctx(pgn, "white"))

        assert fact.details["low_clock_threshold_s"] == 30
        assert fact.details["moves_in_low_clock"] == 0
        assert fact.severity == "note"

    def test_games_without_clocks_are_skipped(self) -> None:
        assert time_trouble.detect(game_ctx("1. e4 e5 2. Nf3 *", "white")) == []

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("600", 600), ("600+5", 600), ("180+2", 180),
            ("-", None), ("?", None), ("1/259200", None), (None, None),
        ],
    )  # fmt: skip
    def test_base_time_from_the_header(self, header: str | None, expected: int | None) -> None:
        assert time_trouble.base_time_s(header) == expected


def test_per_move_detectors_only_run_on_flagged_user_moves() -> None:
    # Flat evals: nothing is an inaccuracy, so only the game-level pawn summary appears.
    facts = run_detectors(game_ctx("1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 *", "white"))

    assert [(f.theme, f.ply) for f in facts] == [("pawn_structure", None)]
