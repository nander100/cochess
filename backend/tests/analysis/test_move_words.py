"""Move tags' words (SPEC_V3 §9.4): captures, checks, castling, promotion."""

import pytest

from app.analysis.move_words import san_words


@pytest.mark.parametrize(
    ("san", "words"),
    [
        ("Nf3", "knight to f3"),
        ("Nxe5", "knight takes on e5"),
        ("Nbd7", "knight to d7"),
        ("R1e2", "rook to e2"),
        ("e4", "pawn to e4"),
        ("exd5", "pawn takes on d5"),
        ("Qxh7+", "queen takes on h7, with check"),
        ("Qxf7#", "queen takes on f7, checkmate"),
        ("O-O", "castles kingside"),
        ("O-O-O+", "castles queenside, with check"),
        ("0-0", "castles kingside"),
        ("e8=Q", "pawn to e8, promoting to a queen"),
        ("exd8=N+", "pawn takes on d8, promoting to a knight, with check"),
        ("Kxg2", "king takes on g2"),
        ("Bb5!?", "bishop to b5"),
    ],
)
def test_words_for_each_kind_of_move(san: str, words: str) -> None:
    assert san_words(san) == words


@pytest.mark.parametrize("text", ["", "knight", "Zz9", "e9", "O-O-O-O"])
def test_anything_else_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="not a move"):
        san_words(text)
