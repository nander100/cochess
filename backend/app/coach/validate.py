"""Move-mention validation (SPEC §7.4): every move the coach writes must be in the data.

Tokens checked: piece moves (Nf3, Bxe5, Qh8+), pawn captures (exd5), promotions (e8=Q),
castling, anything with a check/mate sign, and bare pawn moves written as moves (after a move
number: "14. d4", "14...d5"). Bare squares in prose ("the e4 pawn") are not moves (PLAN Q23).
"""

import re
from collections.abc import Iterable, Iterator
from typing import Any

_SAN = re.compile(
    r"""
    (?<![\w])
    (?:
        (?P<castle>(?:O-O(?:-O)?|0-0(?:-0)?)[+\#]?)
      | (?P<piece>[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+\#]?)
      | (?P<pawn_capture>[a-h]x[a-h][1-8](?:=[QRBN])?[+\#]?)
      | (?P<pawn_marked>[a-h][1-8](?:=[QRBN][+\#]?|[+\#]))
      | \d+\.(?:\.\.)?\s?(?P<numbered>[a-h][1-8](?:=[QRBN])?[+\#]?)
    )
    (?![\w])
    """,
    re.VERBOSE,
)
REMOVED = "[move removed]"
# A whole token that is a SAN move, for reading the data side. Bare pawn moves count here
# ("1. e4 e5"): in data every token is a move; in the coach's prose a bare square usually isn't.
_FULL_SAN = re.compile(
    r"(?:O-O(?:-O)?|0-0(?:-0)?|[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?"
    r"|[a-h](?:x[a-h])?[1-8](?:=[QRBN])?)[+#]?"
)
_MOVE_NUMBER = re.compile(r"^\d+\.+")
_ANNOTATION = re.compile(r"[!?]+$")  # "Bb5??" in the annotated movetext


def _matches(text: str) -> Iterator[tuple[int, int, str]]:
    """(start, end, token) for every move-like token, spanning only the move itself."""
    for match in _SAN.finditer(text):
        group = next(name for name, value in match.groupdict().items() if value)
        yield match.start(group), match.end(group), match.group(group)


def normalize(token: str) -> str:
    """Compare moves without check/mate signs, and with castling spelled with letters."""
    return token.rstrip("+#").replace("0-0-0", "O-O-O").replace("0-0", "O-O")


def extract_moves(text: str) -> list[str]:
    return [token for _, _, token in _matches(text)]


def allowed_moves(data: Any, *, skip_keys: Iterable[str] = ("user_prompt",)) -> set[str]:
    """Every move found in any string of a JSON-like structure. The user's own message is skipped:
    the player suggesting a move doesn't make it engine data."""
    skip = set(skip_keys)
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, str):
            for word in value.split():
                token = _ANNOTATION.sub("", _MOVE_NUMBER.sub("", word))
                if _FULL_SAN.fullmatch(token):
                    found.add(normalize(token))
        elif isinstance(value, dict):
            for key, item in value.items():
                if key not in skip:
                    walk(item)
        elif isinstance(value, list | tuple):
            for item in value:
                walk(item)

    walk(data)
    return found


def find_invalid(text: str, allowed: set[str]) -> list[str]:
    """Moves in `text` that aren't in `allowed`, in order of first appearance, without repeats."""
    invalid: list[str] = []
    for token in extract_moves(text):
        if normalize(token) not in allowed and token not in invalid:
            invalid.append(token)
    return invalid


def strip_moves(text: str, invalid: Iterable[str]) -> str:
    """Replace each invalid move with a visible placeholder."""
    bad = {normalize(token) for token in invalid}
    pieces, last = [], 0
    for start, end, token in _matches(text):
        if normalize(token) in bad:
            pieces.append(text[last:start])
            pieces.append(REMOVED)
            last = end
    pieces.append(text[last:])
    return "".join(pieces)
