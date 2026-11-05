"""Checking saved variations before they're stored (SPEC_V3 §5.1)."""

import pytest

from app.analysis.pgn import parse_pgn
from app.analysis.variations import SavedVariation, VariationError, check_variations
from app.config import Limits
from tests.pgn_fixtures import read_pgn

OPERA = parse_pgn(read_pgn("opera_game.pgn"), max_chars=100_000, max_plies=600)
LIMITS = Limits()


def test_legal_variations_are_kept_in_order_and_repeats_dropped() -> None:
    first = SavedVariation(start_path=["e2e4", "e7e5"], moves=["f1c4"])
    second = SavedVariation(start_path=["e2e4", "e7e5", "f1c4"], moves=["g8f6"])

    assert check_variations(OPERA, [first, second, first], LIMITS) == [first, second]


def test_an_illegal_move_names_the_variation() -> None:
    bad = SavedVariation(start_path=["e2e4"], moves=["e7e5", "e1e3"])

    with pytest.raises(VariationError, match=r"Variation 2: .*\(e1e3\) isn't legal"):
        check_variations(OPERA, [SavedVariation(start_path=[], moves=["d2d4"]), bad], LIMITS)


def test_an_illegal_start_path_is_rejected() -> None:
    with pytest.raises(VariationError, match="Variation 1"):
        check_variations(OPERA, [SavedVariation(start_path=["e2e5"], moves=["e7e5"])], LIMITS)


def test_garbage_moves_are_rejected() -> None:
    with pytest.raises(VariationError, match="isn't a valid move"):
        check_variations(OPERA, [SavedVariation(start_path=[], moves=["hello"])], LIMITS)


def test_limits_on_count_and_length() -> None:
    small = Limits(max_variations=1, max_variation_moves=2)
    one = SavedVariation(start_path=[], moves=["d2d4"])

    with pytest.raises(VariationError, match="Too many variations"):
        check_variations(OPERA, [one, SavedVariation(start_path=[], moves=["c2c4"])], small)
    with pytest.raises(VariationError, match="too long"):
        check_variations(
            OPERA, [SavedVariation(start_path=[], moves=["d2d4", "d7d5", "c2c4"])], small
        )
