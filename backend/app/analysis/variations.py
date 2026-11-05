"""Saved variations (SPEC_V3 §5.1): lines the player explored, each a starting path plus its
moves, both UCI. Every one is replayed from the start with python-chess before it's stored."""

from collections.abc import Sequence

from pydantic import BaseModel, Field

from app.analysis.paths import PathError, resolve_path
from app.analysis.pgn import ParsedGame
from app.config import Limits


class SavedVariation(BaseModel):
    """A line the player explored: where it starts and its moves, both UCI."""

    start_path: list[str] = Field(max_length=600)
    moves: list[str] = Field(min_length=1, max_length=600)


class VariationError(Exception):
    """A variation can't be saved. `message` is safe to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def check_variations(
    parsed: ParsedGame, variations: Sequence[SavedVariation], limits: Limits
) -> list[SavedVariation]:
    """Every variation replayed from the start; exact repeats dropped. Raises VariationError."""
    if len(variations) > limits.max_variations:
        raise VariationError(f"Too many variations (limit {limits.max_variations}).")
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    kept = []
    for number, variation in enumerate(variations, start=1):
        if len(variation.moves) > limits.max_variation_moves:
            raise VariationError(
                f"Variation {number} is too long (limit {limits.max_variation_moves} moves)."
            )
        try:
            resolve_path(parsed, [*variation.start_path, *variation.moves], limits.max_plies)
        except PathError as error:
            raise VariationError(f"Variation {number}: {error.message}") from error
        key = (tuple(variation.start_path), tuple(variation.moves))
        if key not in seen:
            seen.add(key)
            kept.append(variation)
    return kept
