"""The onboarding assessment (SPEC_V2 §10): split a paste into games, categorize time controls,
and decide which of the 12 slots each game fills. Pure: no database, no engine."""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from app.analysis.evals import Color
from app.analysis.game_info import UserResult
from app.analysis.pgn import ParsedGame, PgnError, parse_pgn
from app.config import Limits, OnboardingSettings

Category = Literal["bullet", "blitz", "rapid", "classical", "correspondence"]
Slot = Literal["white_win", "white_loss", "black_win", "black_loss"]
SLOTS: tuple[Slot, ...] = ("white_win", "white_loss", "black_win", "black_loss")
Reason = Literal[
    "invalid_pgn",  # can't be analyzed: illegal move, non-standard start, ... (see the error)
    "duplicate",  # already uploaded, or earlier in this paste
    "needs_color",  # the player hasn't said which side they played
    "needs_time_control",  # no TimeControl header: the player picks the category
    "wrong_time_control",
    "unfinished",
    "draw",
    "slot_full",
]

_INCREMENT = re.compile(r"^(\d+)(?:\+(\d+))?$")
_CORRESPONDENCE = re.compile(r"^\d+/\d+$")  # "1/259200": one move per N seconds
_RESULT_AT_END = re.compile(r"(1-0|0-1|1/2-1/2|\*)\s*$")
_ESTIMATED_MOVES = 40
_SLOTS: dict[tuple[Color, UserResult], Slot] = {
    ("white", "win"): "white_win",
    ("white", "loss"): "white_loss",
    ("black", "win"): "black_win",
    ("black", "loss"): "black_loss",
}


@dataclass(frozen=True)
class SplitGame:
    """One game from a paste: parsed, or why it can't be."""

    text: str
    game: ParsedGame | None
    error: PgnError | None


@dataclass(frozen=True)
class Candidate:
    """A game the player wants to use, as they described it."""

    color: Color | None
    result: UserResult | None  # for the player; None for an unfinished game
    category: Category | None  # from the header, or the player's pick
    invalid: bool = False
    duplicate: bool = False


@dataclass(frozen=True)
class SlotDecision:
    slot: Slot | None
    reason: Reason | None  # why it fills no slot


def split_games(text: str, limits: Limits, settings: OnboardingSettings) -> list[SplitGame]:
    """Split a paste of one or more PGNs. Raises PgnError("too_large") over the paste limits.

    A new game starts at a header line after the current game's moves, or at any line after a
    game result ("1-0", "0-1", "1/2-1/2", "*"), so games without headers split too.
    """
    if len(text) > settings.max_paste_chars:
        raise PgnError(
            "too_large", f"That's too much text (limit {settings.max_paste_chars:,} characters)."
        )
    chunks = [chunk for chunk in _chunks(text) if chunk.strip()]
    if len(chunks) > settings.max_paste_games:
        raise PgnError("too_large", f"Paste at most {settings.max_paste_games} games at a time.")
    games = []
    for chunk in chunks:
        try:
            parsed = parse_pgn(chunk, max_chars=limits.max_pgn_chars, max_plies=limits.max_plies)
            games.append(SplitGame(text=chunk, game=parsed, error=None))
        except PgnError as error:
            games.append(SplitGame(text=chunk, game=None, error=error))
    return games


def _chunks(text: str) -> list[str]:
    chunks: list[list[str]] = [[]]
    has_moves = ended = False
    for line in text.splitlines():
        stripped = line.strip()
        is_header = stripped.startswith("[")
        if stripped and ((is_header and has_moves) or ended):
            chunks.append([])
            has_moves = ended = False
        chunks[-1].append(line)
        if stripped and not is_header:
            has_moves = True
            ended = _RESULT_AT_END.search(stripped) is not None
    return ["\n".join(lines) for lines in chunks]


def time_control_category(header: str | None, settings: OnboardingSettings) -> Category | None:
    """Lichess's categories from the TimeControl header: estimated duration = base + 40 x
    increment. None when the header doesn't say ("-", "?", missing): the player picks."""
    value = (header or "").strip()
    if _CORRESPONDENCE.match(value):
        return "correspondence"
    match = _INCREMENT.match(value)
    if match is None:
        return None
    estimate = int(match.group(1)) + _ESTIMATED_MOVES * int(match.group(2) or 0)
    if estimate < settings.bullet_below_s:
        return "bullet"  # ultrabullet included
    if estimate < settings.blitz_below_s:
        return "blitz"
    if estimate < settings.rapid_below_s:
        return "rapid"
    return "classical"


def assign_slots(
    filled: Mapping[Slot, int],
    candidates: Sequence[Candidate],
    primary: Category,
    settings: OnboardingSettings,
) -> list[SlotDecision]:
    """Which slot each candidate fills, in order, given the slots already filled; or why not."""
    counts: Counter[Slot] = Counter(filled)
    decisions = []
    for candidate in candidates:
        decision = _decide(candidate, counts, primary, settings)
        if decision.slot is not None:
            counts[decision.slot] += 1
        decisions.append(decision)
    return decisions


def _decide(
    candidate: Candidate, counts: Counter[Slot], primary: Category, settings: OnboardingSettings
) -> SlotDecision:
    def rejected(reason: Reason) -> SlotDecision:
        return SlotDecision(slot=None, reason=reason)

    if candidate.invalid:
        return rejected("invalid_pgn")
    if candidate.duplicate:
        return rejected("duplicate")
    if candidate.color is None:
        return rejected("needs_color")
    if candidate.category is None:
        return rejected("needs_time_control")
    if candidate.category != primary:
        return rejected("wrong_time_control")
    if candidate.result is None:
        return rejected("unfinished")
    if candidate.result == "draw":
        return rejected("draw")
    slot = _SLOTS[(candidate.color, candidate.result)]
    if counts[slot] >= settings.games_per_slot:
        return rejected("slot_full")
    return SlotDecision(slot=slot, reason=None)


def suggest_colors(games: Sequence[ParsedGame | None]) -> list[Color | None]:
    """The side the player probably played in each game: the name that appears in more than
    half the pasted games (and at least two) is taken to be theirs. The player confirms."""
    names: Counter[str] = Counter()
    for game in games:
        if game is not None:
            names.update({_name(game, "White"), _name(game, "Black")} - {""})
    common = [(name, count) for name, count in names.most_common(2)]
    parsed = sum(game is not None for game in games)
    if not common or common[0][1] < 2 or common[0][1] * 2 <= parsed:
        return [None] * len(games)
    if len(common) > 1 and common[1][1] == common[0][1]:
        return [None] * len(games)  # two players in every game: can't tell which is theirs
    name = common[0][0]
    suggestions: list[Color | None] = []
    for game in games:
        if game is not None and _name(game, "White") == name:
            suggestions.append("white")
        elif game is not None and _name(game, "Black") == name:
            suggestions.append("black")
        else:
            suggestions.append(None)
    return suggestions


def _name(game: ParsedGame, side: str) -> str:
    name = game.headers.get(side, "").strip()
    return "" if name in ("?", "Anonymous") else name.casefold()
