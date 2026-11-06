"""Coach board annotations (SPEC_V3 §6): `<board arrows="d1d4:red" squares="d4:red"/>` tags in a
reply are parsed, checked against python-chess and the engine data for the position the message
is about (§6.2), and turned into structured annotations. Invalid shapes are dropped and reported;
the frontend never sees the raw markup.

Each valid tag becomes a placeholder link, `[board](cc:board/N)`, at its place in the text, so
react-markdown can render it as a board icon without the text being split (PLAN_V3 adjustment 1).
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import chess
from pydantic import BaseModel

from app.analysis.classify import classify
from app.analysis.engine import EngineResult
from app.analysis.evals import Color, for_color, winning_chances
from app.analysis.moments import Grade
from app.config import CoachSettings, Thresholds

AnnotationColor = Literal["green", "red", "yellow", "blue"]
COLORS: frozenset[str] = frozenset({"green", "red", "yellow", "blue"})
DropReason = Literal[
    "malformed",  # not a tag we can read
    "no_position",  # the reply isn't about one board position (synopsis, baseline report)
    "too_many_tags",
    "too_many_shapes",
    "illegal_arrow",  # no piece on the from-square, or from == to
    "not_in_data",  # neither a move from the data, a threat, nor a plan the engine plays
    "wrong_color",  # a move from the data, in a color its grade doesn't allow
    "moment_leak",  # points out a move the player is meant to find
    "unknown_line",  # a line link that names no line in the data (SPEC_V3 §9.4)
    "too_many_links",
]

BOARD_TAG = re.compile(r"<\s*/?\s*board\b[^<>]*>", re.IGNORECASE)
_OPEN = re.compile(r"^<\s*board\b", re.IGNORECASE)
_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_ATTR_LIST = re.compile(r'^\s*(?:\w+\s*=\s*"[^"]*"\s*)*/?\s*$')
_ARROW = re.compile(r"^([a-h][1-8])([a-h][1-8]):(\w+)$")
_SQUARE = re.compile(r"^([a-h][1-8]):(\w+)$")
PLACEHOLDER = "[board](cc:board/{index})"


class Arrow(BaseModel):
    orig: str
    dest: str
    color: AnnotationColor


class SquareMark(BaseModel):
    square: str
    color: AnnotationColor


class Annotation(BaseModel):
    """One valid tag: its shapes and where its placeholder starts in the display text."""

    tag_index: int
    char_offset: int
    arrows: list[Arrow]
    squares: list[SquareMark]


class Dropped(BaseModel):
    tag: str  # the tag as the coach wrote it
    reason: DropReason
    shape: str | None = None  # "d1d4:red" / "d4:red"; None when the whole tag was dropped


@dataclass(frozen=True)
class BoardFacts:
    """What the coach was given about position P (SPEC_V3 §6.2).

    `graded` holds every move from the data that starts in P, keyed by its first four UCI
    characters (from + to), with its grade when one is known (None: blue only). `mistake` is the
    game's own mistake from P, which may be red whatever its grade. `plan_moves` are the
    from/to squares of every move in the engine lines from P. While a moment is unrevealed,
    `banned` holds the moves the player must find and `known` the moves they already know about
    (the game's move, their tries): an arrow showing a known move isn't a leak.
    """

    fen: str
    graded: Mapping[str, Grade | None] = field(default_factory=dict)
    mistake: str | None = None
    plan_moves: frozenset[str] = frozenset()
    banned: frozenset[str] = frozenset()
    known: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AnnotatedText:
    text: str  # for display: valid tags replaced by placeholders, invalid ones removed
    raw: str  # for the conversation history: only the valid tags, rewritten
    annotations: list[Annotation]
    dropped: list[Dropped]

    @property
    def leaked(self) -> bool:
        return any(d.reason == "moment_leak" for d in self.dropped)


# --- Facts about P ---


def engine_grades(
    board: chess.Board, result: EngineResult, thresholds: Thresholds, best_margin: float
) -> dict[str, Grade]:
    """The grade of each engine line's first move, against the best line (as `moments.grade`)."""
    mover: Color = "white" if board.turn == chess.WHITE else "black"
    best = winning_chances(result.evaluation())
    grades: dict[str, Grade] = {}
    for rank, line in enumerate(result.lines):
        drop = for_color(best - winning_chances(line.evaluation()), mover)
        grade: Grade
        if rank == 0 or drop < best_margin:
            grade = "best"
        elif drop < thresholds.inaccuracy:
            grade = "good"
        else:
            grade = classify(drop, thresholds) or "inaccuracy"
        grades.setdefault(line.moves_uci[0][:4], grade)
    return grades


def plan_moves(result: EngineResult | None) -> frozenset[str]:
    """from+to of every move in the engine lines from P, either side's."""
    if result is None:
        return frozenset()
    return frozenset(move[:4] for line in result.lines for move in line.moves_uci)


def san_to_keys(fen: str, sans: Iterable[str]) -> frozenset[str]:
    """from+to keys of SAN moves legal in `fen` (anything that doesn't parse is skipped)."""
    board = chess.Board(fen)
    keys = set()
    for san in sans:
        try:
            keys.add(board.parse_san(san).uci()[:4])
        except ValueError:
            continue
    return frozenset(keys)


# --- Parsing and checking ---


def annotate(text: str, facts: BoardFacts | None, limits: CoachSettings) -> AnnotatedText:
    """Check every board tag in `text`; `facts` is None for replies with no board position."""
    pieces: list[str] = []
    raw_pieces: list[str] = []
    annotations: list[Annotation] = []
    dropped: list[Dropped] = []
    last = 0
    for match in BOARD_TAG.finditer(text):
        tag = match.group(0)
        before = text[last : match.start()]
        last = match.end()
        arrows, squares = check_tag(tag, facts, limits, len(annotations), dropped)
        if arrows or squares:
            index = len(annotations)
            pieces.append(before)
            raw_pieces.append(before)
            offset = sum(len(p) for p in pieces)
            annotations.append(
                Annotation(tag_index=index, char_offset=offset, arrows=arrows, squares=squares)
            )
            pieces.append(PLACEHOLDER.format(index=index))
            raw_pieces.append(serialize(arrows, squares))
        else:
            trimmed = trim_before(before, text[match.end() : match.end() + 1])
            pieces.append(trimmed)
            raw_pieces.append(trimmed)
    pieces.append(text[last:])
    raw_pieces.append(text[last:])
    return AnnotatedText(
        text="".join(pieces), raw="".join(raw_pieces), annotations=annotations, dropped=dropped
    )


def check_tag(
    tag: str,
    facts: BoardFacts | None,
    limits: CoachSettings,
    valid_so_far: int,
    dropped: list[Dropped],
) -> tuple[list[Arrow], list[SquareMark]]:
    if not _OPEN.match(tag):
        return [], []  # a stray closing tag: removed, nothing to report
    if facts is None:
        dropped.append(Dropped(tag=tag, reason="no_position"))
        return [], []
    if valid_so_far >= limits.annotation_max_tags:
        dropped.append(Dropped(tag=tag, reason="too_many_tags"))
        return [], []
    inner = _OPEN.sub("", tag)[:-1]  # without "<board" and ">"
    attrs = dict(_ATTR.findall(inner))
    if not _ATTR_LIST.match(inner) or not attrs or set(attrs) - {"arrows", "squares"}:
        dropped.append(Dropped(tag=tag, reason="malformed"))
        return [], []
    return _check_tokens(
        tag, _tokens(attrs.get("arrows", "")), _tokens(attrs.get("squares", "")), facts, limits,
        dropped,
    )  # fmt: skip


def check_shapes(
    arrows: Sequence[str],
    squares: Sequence[str],
    facts: BoardFacts,
    limits: CoachSettings,
    *,
    label: str,
    tag_index: int = 0,
) -> tuple[Annotation | None, list[Dropped]]:
    """Shapes given as lists ("d1d4:red", "d4:red"), e.g. a walkthrough step's: the same rules
    as a board tag. `label` names their source in the log ("step 3")."""
    dropped: list[Dropped] = []
    # A lone square in the arrows list ("e5:blue") is a highlight written in the wrong list: it's
    # checked as a square, by the square rules.
    arrow_tokens = [a.strip() for a in arrows if not _SQUARE.match(a.strip().lower())]
    square_tokens = [s.strip() for s in squares]
    square_tokens += [a.strip() for a in arrows if _SQUARE.match(a.strip().lower())]
    kept_arrows, kept_squares = _check_tokens(
        label, arrow_tokens, square_tokens, facts, limits, dropped
    )
    if not kept_arrows and not kept_squares:
        return None, dropped
    annotation = Annotation(
        tag_index=tag_index, char_offset=0, arrows=kept_arrows, squares=kept_squares
    )
    return annotation, dropped


def _check_tokens(
    tag: str,
    arrow_tokens: Sequence[str],
    square_tokens: Sequence[str],
    facts: BoardFacts,
    limits: CoachSettings,
    dropped: list[Dropped],
) -> tuple[list[Arrow], list[SquareMark]]:
    board = chess.Board(facts.fen)
    arrows: list[Arrow] = []
    for token in arrow_tokens:
        arrow = _parse_arrow(token)
        reason: DropReason | None
        if arrow is None:
            reason = "malformed"
        elif len(arrows) >= limits.annotation_max_arrows:
            reason = "too_many_shapes"
        else:
            reason = _arrow_problem(arrow, board, facts)
        if reason is None and arrow is not None:
            arrows.append(arrow)
        else:
            dropped.append(Dropped(tag=tag, reason=reason or "malformed", shape=token))
    squares: list[SquareMark] = []
    for token in square_tokens:
        mark = _parse_square(token)
        if mark is None:
            reason = "malformed"
        elif len(squares) >= limits.annotation_max_squares:
            reason = "too_many_shapes"
        else:
            reason = _square_problem(mark, facts)
        if reason is None and mark is not None:
            squares.append(mark)
        else:
            dropped.append(Dropped(tag=tag, reason=reason or "malformed", shape=token))
    return arrows, squares


def _tokens(value: str) -> list[str]:
    """Shapes separated by commas (the format) or spaces (a common slip)."""
    return [token for token in re.split(r"[,\s]+", value) if token]


def _parse_arrow(token: str) -> Arrow | None:
    match = _ARROW.match(token.lower())
    if match is None or match.group(3) not in COLORS:
        return None
    return Arrow.model_validate({"orig": match[1], "dest": match[2], "color": match[3]})


def _parse_square(token: str) -> SquareMark | None:
    match = _SQUARE.match(token.lower())
    if match is None or match.group(2) not in COLORS:
        return None
    return SquareMark.model_validate({"square": match[1], "color": match[2]})


def _banned_squares(facts: BoardFacts) -> set[str]:
    return {key[:2] for key in facts.banned} | {key[2:4] for key in facts.banned}


def _arrow_problem(arrow: Arrow, board: chess.Board, facts: BoardFacts) -> DropReason | None:
    key = arrow.orig + arrow.dest
    if facts.banned and (
        key in facts.banned
        or (key not in facts.known and {arrow.orig, arrow.dest} & _banned_squares(facts))
    ):
        return "moment_leak"
    orig = chess.parse_square(arrow.orig)
    dest = chess.parse_square(arrow.dest)
    if orig == dest or board.piece_at(orig) is None:
        return "illegal_arrow"
    # A move from the data is judged by its grade alone, so a red or green arrow on it always
    # means what its grade says (a capture can't pass as a "threat" in the wrong color).
    if key in facts.graded and _is_legal(board, orig, dest):
        ok = _move_color_ok(arrow.color, facts.graded[key], key == facts.mistake)
        return None if ok else "wrong_color"
    # A threat: the piece on `orig` attacks an enemy piece on `dest`, for either side. Never green.
    if arrow.color in ("red", "yellow") and _is_threat(board, orig, dest):
        return None
    # A plan: a move the engine actually plays somewhere in its lines from P.
    if arrow.color == "blue" and key in facts.plan_moves:
        return None
    return "not_in_data"


def _is_threat(board: chess.Board, orig: int, dest: int) -> bool:
    attacker, target = board.piece_at(orig), board.piece_at(dest)
    return (
        attacker is not None
        and target is not None
        and attacker.color != target.color
        and dest in board.attacks(orig)
    )


def _square_problem(mark: SquareMark, facts: BoardFacts) -> DropReason | None:
    if facts.banned and mark.square in _banned_squares(facts):
        return "moment_leak"
    return None


def _is_legal(board: chess.Board, orig: int, dest: int) -> bool:
    return any(m.from_square == orig and m.to_square == dest for m in board.legal_moves)


def _move_color_ok(color: str, grade: Grade | None, is_game_mistake: bool) -> bool:
    if color == "blue":
        return True
    if color == "green":
        return grade in ("best", "good")
    if color == "red":
        return is_game_mistake or grade in ("mistake", "blunder")
    return grade == "inaccuracy"  # yellow


def serialize(arrows: list[Arrow], squares: list[SquareMark]) -> str:
    attrs = []
    if arrows:
        attrs.append(f'arrows="{",".join(f"{a.orig}{a.dest}:{a.color}" for a in arrows)}"')
    if squares:
        attrs.append(f'squares="{",".join(f"{s.square}:{s.color}" for s in squares)}"')
    return f"<board {' '.join(attrs)}/>"


def trim_before(before: str, after: str) -> str:
    """Drop the space before a removed tag when the tag was followed by a space, punctuation or
    the end, so "gone <board .../>, so" reads "gone, so"."""
    if before.endswith(" ") and (not after or after in " ,.;:!?)\n"):
        return before[:-1]
    return before
