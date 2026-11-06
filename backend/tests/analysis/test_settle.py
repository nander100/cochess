"""Where line playback stops (SPEC_V3 §9.6), on hand-built lines: a simple piece win, an
exchange that ends even (never stopping mid-exchange), a mate, a quiet line; and the caption."""

import chess
import pytest

from app.analysis.evals import Evaluation
from app.analysis.settle import caption, settle
from app.config import PlaybackSettings

S = PlaybackSettings()
START = chess.STARTING_FEN


def unknown(moves: list[str]) -> list[Evaluation | None]:
    return [None] * (len(moves) + 1)


def test_a_simple_piece_win_stops_once_the_reply_is_shown() -> None:
    fen = "4k3/8/8/3n4/8/8/8/3QK3 w - - 0 1"  # the knight on d5 hangs
    moves = ["d1d5", "e8e7", "d5b7", "e7e6"]

    result = settle(fen, moves, unknown(moves), 2, S)

    assert result.settle_ply == 2  # not after the capture alone: the reply is always shown
    assert result.caption == "White has won a knight."


def test_an_exchange_is_never_cut_in_the_middle_and_an_even_one_plays_out() -> None:
    fen = "4k3/8/3p4/4n3/8/5N2/P6P/4K3 w - - 0 1"
    moves = ["a2a3", "e8e7", "f3e5", "d6e5", "h2h3", "e7d6"]

    result = settle(fen, moves, unknown(moves), 2, S)

    # After 2. Nxe5 White is a knight up, but Black's next move takes back: no stop there.
    assert result.settle_ply == len(moves)
    assert result.caption == "The position has settled."


def test_checkmate_stops_at_once() -> None:
    moves = ["f2f3", "e7e5", "g2g4", "d8h4"]
    assert settle(START, moves, unknown(moves), 2, S).settle_ply == 4
    assert settle(START, moves, unknown(moves), 2, S).caption == "White is checkmated."
    after_g4 = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq g3 0 2"
    assert settle(after_g4, ["d8h4"], [None, None], 2, S).settle_ply == 1  # before the minimum


def test_a_quiet_line_plays_to_the_end() -> None:
    moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
    evals = [Evaluation(cp=20)] * 5

    result = settle(START, moves, evals, 2, S)

    assert result.settle_ply == 4
    assert result.caption == "The position is about equal."


def test_a_big_swing_in_win_chances_stops_when_the_position_is_quiet() -> None:
    moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
    evals = [Evaluation(cp=0), Evaluation(cp=0), Evaluation(cp=700), Evaluation(cp=700), None]

    result = settle(START, moves, evals, 2, S)

    assert result.settle_ply == 2
    assert result.caption == "White is winning."


def test_the_swing_is_measured_for_the_side_that_starts_the_line() -> None:
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"  # Black to move
    moves = ["e7e5", "g1f3", "b8c6"]
    evals = [Evaluation(cp=0), Evaluation(cp=-500), Evaluation(cp=-500), Evaluation(cp=-500)]

    result = settle(fen, moves, evals, 2, S)

    assert result.settle_ply == 2
    assert result.caption == "Black is winning."


def test_after_a_try_two_more_plies_are_shown() -> None:
    fen = "4k3/8/8/3n4/8/8/8/3QK3 w - - 0 1"
    moves = ["d1d5", "e8e7", "d5a8", "e7e6"]  # 3. Qa8 is quiet (no check)

    assert settle(fen, moves, unknown(moves), S.settle_min_plies_after_try, S).settle_ply == 3


@pytest.mark.parametrize(
    ("start", "stop", "text"),
    [
        ("4k3/8/8/8/8/8/8/R3K2r w - - 0 1", "4k3/8/8/8/8/8/8/4K2R w - - 0 1",
         "White has won a rook."),
        ("4k3/8/8/8/8/8/1N6/4K3 w - - 0 1", "4k3/8/8/8/8/8/8/4K3 w - - 0 1",
         "Black has won a knight."),
        ("r3k3/pp6/8/8/8/8/1N6/4K3 w - - 0 1", "4k3/8/8/8/8/8/8/4K3 w - - 0 1",
         "White has won a rook and two pawns for a knight."),
        ("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1", "4k3/8/8/4P3/8/8/8/4K3 w - - 0 1",
         "White is slightly better."),
    ],
)  # fmt: skip
def test_the_caption_says_what_changed(start: str, stop: str, text: str) -> None:
    evaluation = Evaluation(cp=100)
    assert caption(chess.Board(start), chess.Board(stop), evaluation, S) == text


def test_a_new_passed_pawn_is_named() -> None:
    start = "4k3/3p4/8/4P3/8/8/8/4K3 w - - 0 1"
    stop = "4k3/8/8/4P3/8/8/8/4K3 w - - 0 1"  # the d-pawn is gone: e5 is now passed
    assert caption(chess.Board(start), chess.Board(stop), None, S) == "White now has a passed pawn."


def test_bad_input_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one move"):
        settle(START, [], [None], 2, S)
    with pytest.raises(ValueError, match="not legal"):
        settle(START, ["e2e5"], [None, None], 2, S)
