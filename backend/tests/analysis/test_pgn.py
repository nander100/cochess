from pathlib import Path

import chess
import pytest

from app.analysis.pgn import ParsedGame, PgnError, PgnErrorCode, parse_pgn
from tests.pgn_fixtures import OWNER_USERNAME, USER_FIXTURES, owner_color, read_pgn

STANDARD_FEN_HEADER = f'[SetUp "1"]\n[FEN "{chess.STARTING_FEN}"]\n\n'
ANNOTATED_MAINLINE = [
    "e4", "e5", "Nf3", "Nc6", "Bc4", "Nd4", "Nxe5",
    "Qg5", "Nxf7", "Qxg2", "Rf1", "Qxe4+", "Be2", "Nf3#",
]  # fmt: skip


def parse(text: str, *, max_chars: int = 100_000, max_plies: int = 600) -> ParsedGame:
    return parse_pgn(text, max_chars=max_chars, max_plies=max_plies)


def expect_error(text: str, code: PgnErrorCode, **limits: int) -> PgnError:
    with pytest.raises(PgnError) as info:
        parse(text, **limits)
    assert info.value.code == code
    return info.value


class TestValidGames:
    def test_parses_every_ply_of_a_complete_game(self) -> None:
        parsed = parse(read_pgn("opera_game.pgn"))

        assert len(parsed.positions) == 33
        first, last = parsed.positions[0], parsed.positions[-1]
        assert (first.ply, first.fen_before, first.san, first.uci) == (
            1,
            chess.STARTING_FEN,
            "e4",
            "e2e4",
        )
        assert (last.ply, last.san) == (33, "Rd8#")
        assert parsed.headers["White"] == "Paul Morphy"

    def test_fen_before_is_the_position_before_each_move(self) -> None:
        parsed = parse(read_pgn("opera_game.pgn"))

        board = chess.Board()
        for position in parsed.positions:
            assert position.fen_before == board.fen()
            board.push_uci(position.uci)
        assert parsed.final_fen == board.fen()

    def test_checkmate_final_position_is_terminal(self) -> None:
        assert parse(read_pgn("opera_game.pgn")).final_is_terminal is True

    def test_unfinished_game_is_not_terminal(self) -> None:
        parsed = parse("1. e4 e5 2. Nf3 *")

        assert parsed.final_is_terminal is False
        assert [p.san for p in parsed.positions] == ["e4", "e5", "Nf3"]

    def test_bare_movetext_without_headers_is_accepted(self) -> None:
        assert len(parse("1.d4 d5 2.c4").positions) == 3

    def test_standard_start_fen_header_is_accepted(self) -> None:
        assert len(parse(STANDARD_FEN_HEADER + "1. e4 e5 *").positions) == 2

    def test_explicit_standard_variant_is_accepted(self) -> None:
        assert len(parse('[Variant "Standard"]\n\n1. e4 *').positions) == 1

    def test_trailing_blank_lines_are_not_a_second_game(self) -> None:
        assert len(parse("1. e4 e5 *\n\n\n   \n").positions) == 2


class TestAnnotations:
    def test_variations_are_stripped_from_the_main_line(self) -> None:
        parsed = parse(read_pgn("annotated_clock_game.pgn"))

        assert [p.san for p in parsed.positions] == ANNOTATED_MAINLINE

    def test_clock_values_are_preserved_in_seconds(self) -> None:
        parsed = parse(read_pgn("annotated_clock_game.pgn"))

        assert [p.clock_s for p in parsed.positions][:6] == [600, 600, 598, 597, 590, 580]

    def test_moves_without_clock_comments_have_no_clock(self) -> None:
        parsed = parse("1. e4 {[%clk 0:05:00]} e5 2. Nf3 *")

        assert [p.clock_s for p in parsed.positions] == [300, None, None]

    def test_stored_pgn_keeps_only_moves_and_clocks(self) -> None:
        parsed = parse(read_pgn("annotated_clock_game.pgn"))

        assert "[%clk 0:09:57]" in parsed.pgn
        assert "Book move" not in parsed.pgn
        assert "$1" not in parsed.pgn
        assert "d6" not in parsed.pgn  # the variation

    def test_stored_pgn_round_trips(self) -> None:
        parsed = parse(read_pgn("annotated_clock_game.pgn"))

        reparsed = parse(parsed.pgn)

        assert reparsed.positions == parsed.positions


class TestRejections:
    def test_illegal_white_move_reports_move_number_and_side(self) -> None:
        # 4. Qh5 is illegal: the knight on f3 blocks the queen's diagonal.
        error = expect_error("1. e4 e5 2. Nf3 Nc6 3. Bb5 Ke7 4. Qh5 Ke8 *", "illegal_move")

        assert error.move_number == 4
        assert error.message == "Move 4 (White): Qh5 is not a legal move in that position."

    def test_illegal_black_move_reports_black(self) -> None:
        error = expect_error("1. e4 e5 2. Nf3 Nf3 *", "illegal_move")

        assert error.move_number == 2
        assert "(Black): Nf3" in error.message

    def test_ambiguous_move_is_explained(self) -> None:
        # Both the b1 and f3 knights can reach d2.
        error = expect_error("1. Nf3 Nf6 2. d3 d6 3. Nd2 *", "illegal_move")

        assert error.move_number == 3
        assert "ambiguous" in error.message

    def test_invalid_move_token_is_reported(self) -> None:
        error = expect_error("1. e4 e5 2. P@e4 *", "illegal_move")

        assert error.message == "Move 2 (White): P@e4 isn't a valid move."

    @pytest.mark.parametrize("null_move", ["--", "Z0", "0000"])
    def test_null_moves_are_rejected(self, null_move: str) -> None:
        error = expect_error(f"1. e4 e5 2. {null_move} Nc6 *", "illegal_move")

        assert error.message == "Move 2 (White): null moves (--) aren't allowed."

    def test_illegal_move_inside_a_variation_is_ignored(self) -> None:
        parsed = parse("1. e4 (1. d4 Kd5) 1... e5 2. Nf3 *")

        assert [p.san for p in parsed.positions] == ["e4", "e5", "Nf3"]

    def test_nested_variations_are_skipped(self) -> None:
        parsed = parse("1. e4 e5 (1... c5 2. Nf3 (2. c3 d5) 2... d6) 2. Nf3 Nc6 *")

        assert [p.san for p in parsed.positions] == ["e4", "e5", "Nf3", "Nc6"]

    def test_text_that_is_not_move_shaped_is_ignored(self) -> None:
        # python-chess's tokenizer only matches move-shaped text; anything else is skipped.
        parsed = parse("1. e4 e5 2. Zz9 Nf3 *")

        assert [p.san for p in parsed.positions] == ["e4", "e5", "Nf3"]

    def test_non_standard_fen_is_rejected(self) -> None:
        pgn = '[SetUp "1"]\n[FEN "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"]\n\n1. e4 *'

        error = expect_error(pgn, "non_standard_start")

        assert error.message == "Non-standard starting positions aren't supported."

    def test_chess960_is_rejected(self) -> None:
        pgn = (
            '[Variant "Chess960"]\n'
            '[FEN "bbqnnrkr/pppppppp/8/8/8/8/PPPPPPPP/BBQNNRKR w HFhf - 0 1"]\n\n1. e4 *'
        )

        error = expect_error(pgn, "unsupported_variant")

        assert "Chess960" in error.message

    def test_chess960_with_standard_setup_is_still_rejected(self) -> None:
        expect_error('[Variant "Chess960"]\n\n1. e4 *', "unsupported_variant")

    def test_other_variants_are_rejected(self) -> None:
        expect_error('[Variant "Crazyhouse"]\n\n1. e4 *', "unsupported_variant")

    def test_multiple_games_are_rejected(self) -> None:
        pgn = read_pgn("opera_game.pgn") + "\n\n" + read_pgn("annotated_clock_game.pgn")

        error = expect_error(pgn, "multiple_games")

        assert error.message == "Please paste one game at a time."

    @pytest.mark.parametrize(
        "text",
        ["", "   \n", "hello, this is not a game", '[Event "Headers only"]\n\n*'],
        ids=["empty", "whitespace", "prose", "headers-only"],
    )
    def test_text_without_moves_is_rejected(self, text: str) -> None:
        expect_error(text, "no_moves")

    def test_oversized_input_is_rejected_before_parsing(self) -> None:
        expect_error("1. e4 e5 2. Nf3 *", "too_large", max_chars=10)

    def test_too_many_plies_is_rejected(self) -> None:
        expect_error(read_pgn("opera_game.pgn"), "too_long", max_plies=10)


@pytest.mark.parametrize("path", USER_FIXTURES, ids=lambda p: p.name)
def test_owner_games_parse_with_the_labelled_color(path: Path) -> None:
    parsed = parse(path.read_text())

    assert parsed.positions
    # The color in the file name must match the side the owner's account played.
    color_header = "White" if owner_color(path) == "white" else "Black"
    assert parsed.headers[color_header] == OWNER_USERNAME
