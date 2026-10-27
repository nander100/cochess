"""Critical-moment selection (SPEC_V2 §8.1), on the Opera Game with chosen evals.

The player is White. An eval of -100 after a White move (from 0.0) is an inaccuracy (0.18 drop),
-150 a mistake (0.27), -300 a blunder (0.50); the position after Black's reply is back at 0.0.
"""

from app.analysis.summary_models import GameSummary
from app.coach.payload import COACH_EXCLUDE
from tests.analysis.test_summary import opera_summary


def errors(after_white_ply: dict[int, int]) -> GameSummary:
    """Evals after the given White plies; every other position is 0.0."""
    return opera_summary({ply + 1: cp for ply, cp in after_white_ply.items()})


def moment_plies(summary: GameSummary) -> list[tuple[int, int, str]]:
    return [(m.index, m.ply, m.label) for m in summary.moments]


def test_all_errors_then_the_biggest_inaccuracy_to_reach_three() -> None:
    summary = errors({3: -150, 9: -100, 15: -300, 21: -110, 27: -105})

    # Two errors (plies 3, 15), then the biggest inaccuracy (21) makes three, in game order.
    assert moment_plies(summary) == [(1, 3, "mistake"), (2, 15, "blunder"), (3, 21, "inaccuracy")]


def test_more_than_six_keeps_the_biggest_drops_in_game_order() -> None:
    summary = errors({1: -150, 5: -300, 9: -150, 13: -300, 17: -160, 21: -300, 25: -155, 29: -300})

    # Eight errors: the four blunders and the two biggest mistakes (-160 at 17, -155 at 25).
    assert [m.ply for m in summary.moments] == [5, 13, 17, 21, 25, 29]
    assert [m.index for m in summary.moments] == [1, 2, 3, 4, 5, 6]


def test_only_inaccuracies_gives_the_three_biggest() -> None:
    summary = errors({3: -100, 7: -120, 11: -110, 15: -130})

    assert [m.ply for m in summary.moments] == [7, 11, 15]


def test_a_clean_game_has_no_moments() -> None:
    assert errors({}).moments == []


def test_a_moment_describes_the_players_move_and_what_goes_wrong() -> None:
    summary = errors({9: -300})

    [moment] = summary.moments
    assert (moment.ply, moment.move_number, moment.side) == (9, 5, "white")
    assert (moment.san, moment.uci, moment.label) == ("Qxf3", "d1f3", "blunder")
    assert (moment.eval_before, moment.eval_after) == ("0.0", "-3.0")
    assert moment.drop == 0.5023  # wc(0) - wc(-300) = 0 - (2 / (1 + e^1.1046) - 1)
    assert moment.fen_before == "rn1qkbnr/ppp2ppp/3p4/4P3/4P3/5b2/PPP2PPP/RNBQKB1R w KQkq - 0 5"
    # The fake engine's line after the move (4 plies), in SAN: what the coach may show.
    assert len(moment.refutation_san) == 4 and moment.refutation_san[0][0].isalpha()


def test_moments_never_reach_the_chat_coach() -> None:
    assert "moments" in COACH_EXCLUDE["game_summary"]
