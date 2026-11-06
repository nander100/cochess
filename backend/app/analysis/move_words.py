"""A move in everyday words, for move tags (SPEC_V3 §9.4): "knight takes on e5", "castles
kingside", "pawn to e8, promoting to a queen, with check". Generated from the SAN, so the words
always match the move the backend validated; the coach never writes them."""

import re

_SAN = re.compile(
    r"^(?P<piece>[KQRBN])?[a-h]?[1-8]?(?P<capture>x)?"
    r"(?P<square>[a-h][1-8])(?:=(?P<promotion>[QRBN]))?$"
)
_PIECES = {"K": "king", "Q": "queen", "R": "rook", "B": "bishop", "N": "knight"}


def san_words(san: str) -> str:
    """Words for a SAN move. Raises ValueError for something that isn't SAN."""
    clean = san.strip().rstrip("!?")
    mark = clean[-1] if clean.endswith(("+", "#")) else ""
    base = clean.rstrip("+#").replace("0", "O")
    if base in ("O-O", "O-O-O"):
        words = "castles kingside" if base == "O-O" else "castles queenside"
    else:
        match = _SAN.match(base)
        if match is None:
            raise ValueError(f"not a move: {san}")
        piece = _PIECES[match["piece"]] if match["piece"] else "pawn"
        action = "takes on" if match["capture"] else "to"
        words = f"{piece} {action} {match['square']}"
        if match["promotion"]:
            words += f", promoting to a {_PIECES[match['promotion']]}"
    if mark == "+":
        words += ", with check"
    elif mark == "#":
        words += ", checkmate"
    return words
