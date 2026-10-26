from app.analysis.evals import Evaluation, winning_chances
from app.analysis.pgn import ParsedGame, parse_pgn
from app.analysis.selection import scan_fens, select_verify_plies, verify_fens
from app.config import Thresholds

NO_SWINGS = Thresholds(verify_top_swings=0)


def cps(*values: int) -> list[Evaluation]:
    return [Evaluation(cp=v) for v in values]


def parse(pgn: str) -> ParsedGame:
    return parse_pgn(pgn, max_chars=10_000, max_plies=100)


class TestSelectVerifyPlies:
    # Positions before plies 1..6, then the final position. White blunders at ply 3.
    EVALS = cps(20, 30, 20, -300, -290, -280, -270)

    def test_flags_user_moves_at_or_above_the_inaccuracy_threshold(self) -> None:
        assert select_verify_plies(self.EVALS, "white", NO_SWINGS) == [3]

    def test_ignores_the_opponents_drops_for_the_threshold_rule(self) -> None:
        # White's blunder isn't a drop for Black, and Black's own moves barely change anything.
        assert select_verify_plies(self.EVALS, "black", NO_SWINGS) == []

    def test_drop_exactly_at_the_threshold_counts(self) -> None:
        drop = winning_chances(Evaluation(cp=20)) - winning_chances(Evaluation(cp=-300))
        thresholds = Thresholds(inaccuracy=drop, verify_top_swings=0)

        assert select_verify_plies(self.EVALS, "white", thresholds) == [3]

    def test_adds_the_largest_swings_by_either_side(self) -> None:
        # Two big swings by either side: to +M3 at ply 3, back to 0.0 at ply 4. No user drops.
        evals = [*cps(0, 0, 0), Evaluation(mate=3), *cps(0, 0)]

        assert select_verify_plies(evals, "black", Thresholds(verify_top_swings=2)) == [3, 4]

    def test_keeps_the_largest_drops_when_over_the_cap(self) -> None:
        # White drops twice: a small one at ply 1 and a big one at ply 3.
        evals = cps(100, -20, -20, -400, -400)
        thresholds = Thresholds(verify_top_swings=0, verify_max_plies=1)

        assert select_verify_plies(evals, "white", thresholds) == [3]

    def test_black_users_drops_are_measured_from_blacks_side(self) -> None:
        # Black's move at ply 2 throws away a winning position.
        evals = cps(-400, -400, 50, 50)

        assert select_verify_plies(evals, "black", NO_SWINGS) == [2]


class TestFens:
    def test_verify_fens_are_before_and_after_each_ply_deduplicated(self) -> None:
        game = parse("1. e4 e5 2. Nf3 *")

        fens = verify_fens(game, [1, 2])

        assert fens == [p.fen_before for p in game.positions[:3]]

    def test_verify_fens_skip_a_terminal_final_position(self) -> None:
        game = parse("1. f3 e5 2. g4 Qh4# 0-1")

        assert verify_fens(game, [4]) == [game.positions[3].fen_before]

    def test_scan_fens_include_a_non_terminal_final_position(self) -> None:
        game = parse("1. e4 e5 *")

        assert scan_fens(game) == [*(p.fen_before for p in game.positions), game.final_fen]

    def test_scan_fens_skip_a_terminal_final_position(self) -> None:
        game = parse("1. f3 e5 2. g4 Qh4# 0-1")

        assert scan_fens(game) == [p.fen_before for p in game.positions]
