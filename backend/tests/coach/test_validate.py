import pytest

from app.coach.validate import (
    REMOVED,
    allowed_moves,
    extract_moves,
    find_invalid,
    normalize,
    strip_moves,
)


@pytest.mark.parametrize(
    ("text", "moves"),
    [
        ("In 14. Nd4 you left the knight loose.", ["Nd4"]),
        ("After 14...exd5 Black recaptured.", ["exd5"]),
        ("Castling long, O-O-O+, or short with 0-0.", ["O-O-O+", "0-0"]),
        ("The pawn promoted with e8=Q, then Qxh7# ended it.", ["e8=Q", "Qxh7#"]),
        ("Rooks on Rad1 or R1e2 and Nbd7 are all moves.", ["Rad1", "R1e2", "Nbd7"]),
        ("**Bxf6!** was strong and Nd4?? was not.", ["Bxf6", "Nd4"]),
        ("A pawn move with check: d5+.", ["d5+"]),
        ("Numbered pawn moves count: 12. d4 and 12...c5.", ["d4", "c5"]),
    ],
)
def test_extracts_moves(text: str, moves: list[str]) -> None:
    assert extract_moves(text) == moves


@pytest.mark.parametrize(
    "text",
    [
        "The e4 pawn and the knight on f3 controlled the d5 square.",
        "Kings and Queens, Nevertheless, Be careful, Rooks belong on open files.",
        "You were +2.0 up, then -M3.",
        "Move 14 was the turning point on the e-file.",
    ],
)
def test_prose_about_pieces_and_squares_is_not_a_move(text: str) -> None:
    assert extract_moves(text) == []


def test_normalize_ignores_check_signs_and_castling_spelling() -> None:
    assert normalize("Qxh7#") == "Qxh7"
    assert normalize("0-0-0+") == "O-O-O"
    assert normalize("0-0") == "O-O"


def test_allowed_moves_come_from_every_string_except_the_users_message() -> None:
    data = {
        "pgn_to_move": "1. e4 e5 2. Nf3",
        "game_summary": {"key_moments": [{"engine_lines": [{"moves_san": ["Bc4", "Nc6"]}]}]},
        "user_prompt": "what about Qh5?",
    }

    assert allowed_moves(data) == {"e4", "e5", "Nf3", "Bc4", "Nc6"}


def test_black_pawn_moves_in_the_game_data_are_allowed_when_written_with_a_number() -> None:
    allowed = allowed_moves({"pgn_to_move": "1. e4 e5 2. Nf3 d6 3. d4 exd4 4. O-O"})

    assert find_invalid("After 1...e5 and 2...d6, Black took with 3...exd4.", allowed) == []
    assert allowed == {"e4", "e5", "Nf3", "d6", "d4", "exd4", "O-O"}


def test_data_words_that_are_not_moves_are_ignored() -> None:
    assert allowed_moves({"white": "Paul Morphy", "opening": "ECO C41", "eval": "+M3"}) == set()


def test_find_invalid_reports_unknown_moves_once_in_order() -> None:
    text = "1. e4 was fine, Nf3+ too, but Qh5 and Ke2 and Qh5 again were not in the data."

    assert find_invalid(text, {"e4", "Nf3"}) == ["Qh5", "Ke2"]


def test_strip_moves_replaces_only_the_invalid_moves() -> None:
    text = "After 3. Bc4 you played 4. Qh5, then 4...Nf6."

    stripped = strip_moves(text, ["Qh5"])

    assert stripped == f"After 3. Bc4 you played 4. {REMOVED}, then 4...Nf6."
    assert find_invalid(stripped, {"Bc4", "Nf6"}) == []
