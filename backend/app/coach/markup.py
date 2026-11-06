"""The coach's markup (SPEC_V3 §6, §9.4): move tags `{{move:Nxe5}}` (optionally numbered,
`{{move:14...Qxd4}}`), line links `{{line:here.engine1|link text}}` and board tags `<board/>`.

`process` reads a reply once and returns both what's wrong with it (to regenerate once) and what
the player sees: each valid tag becomes a placeholder link, `[words](cc:move/N)`,
`[text](cc:line/N)` or `[board](cc:board/N)`, with its token. Bare notation outside a tag is a
problem; in the final text a valid bare move becomes a move tag and an invalid one is removed.
The coach never writes a line's moves: a line link names a line the backend resolves from data.
"""

import re
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from app.analysis.move_words import san_words
from app.coach.annotations import (
    BOARD_TAG,
    Annotation,
    BoardFacts,
    Dropped,
    check_tag,
    serialize,
    trim_before,
)
from app.coach.validate import FULL_SAN, NUMBER_BEFORE, REMOVED, move_tokens, normalize
from app.config import CoachSettings, PuzzleSettings

LineKind = Literal["engine", "refutation", "candidate", "best", "variation"]

MOVE_TAG = re.compile(r"\{\{\s*move\s*:\s*(?P<body>[^{}|]*?)\s*\}\}", re.IGNORECASE)
LINE_TAG = re.compile(
    r"\{\{\s*line\s*:\s*(?P<ref>[^{}|]*?)\s*\|\s*(?P<label>[^{}]*?)\s*\}\}", re.IGNORECASE
)
# Tags, and inline code spans: a move in `backticks` is notation too ("`b5` and then `e4`").
_ANY_TAG = re.compile(r"\{\{[^{}]*\}\}|<\s*/?\s*board\b[^<>]*>|`[^`\n]+`", re.IGNORECASE)
_CODE_MOVE = re.compile(r"^`\s*((?:\d+\s*(?:\.\.\.|…|\.)\s*)?(\S+?))\s*`$")
# A move's words begin a sentence after these (and at the start, or a list item).
_SENTENCE_END = (".", "!", "?", ":", "\n", "-")
PUZZLE_TAG = re.compile(r"\{\{\s*puzzle\s*:\s*(?P<theme>[^{}|]*?)\s*\}\}", re.IGNORECASE)
_NUMBERED = re.compile(r"^(?P<number>\d+)\s*(?P<dots>\.\.\.|…|\.)\s*(?P<san>\S+)$")
_REF = re.compile(r"^(here|km\d+)\.(engine[1-4]|refutation|candidate|best|variation)$")
# Between two moves "in a row": nothing but spaces, punctuation and move numbers.
_RUN_GAP = re.compile(r"^[\s,;:.\d\-\u2013\u2014\u2026]*$")  # dashes, ellipsis
_LABEL_UNSAFE = re.compile(r"[\[\]()<>{}]")


class MoveToken(BaseModel):
    index: int
    char_offset: int
    san: str
    words: str
    move_number: int | None = None
    white: bool | None = None  # the side that played it, when the move number says
    sentence_start: bool = False  # its words begin a sentence: shown capitalized


class LineLink(BaseModel):
    index: int
    char_offset: int
    line_id: str
    ref: str  # "here.engine1", "km2.refutation"
    label: str
    kind: LineKind
    start_path_uci: list[str]
    moves_uci: list[str]


class PuzzleToken(BaseModel):
    """A recommended puzzle theme (SPEC_V3 §8.2): a chip linking to Lichess's puzzle trainer."""

    index: int
    char_offset: int
    theme: str  # the Lichess slug, e.g. "discoveredAttack"
    label: str  # "Discovered attack"
    url: str


class MessageTokens(BaseModel):
    """A coach message's structured parts, tied to placeholders in its text: stored with the
    message so it shows the same when reloaded (SPEC_V3 §11.2)."""

    moves: list[MoveToken] = []
    line_links: list[LineLink] = []
    annotations: list[Annotation] = []
    puzzles: list[PuzzleToken] = []


@dataclass(frozen=True)
class ResolvedLine:
    start_path_uci: tuple[str, ...]
    moves_uci: tuple[str, ...]
    kind: LineKind


@dataclass(frozen=True)
class Rules:
    """What a reply may contain. `allowed`: every move in the data (normalized SAN). `banned`:
    moves the player must find, at the moment's own number and side (`move_number`,
    `white_to_move`). `numbering`: moves whose number is known, which must be written with it.
    `facts`: the position board tags are drawn on (None: tags dropped). `lines`: the line links
    that resolve; `withheld`: references that would reveal an answer."""

    allowed: frozenset[str]
    limits: CoachSettings
    banned: frozenset[str] = frozenset()
    move_number: int | None = None
    white_to_move: bool | None = None
    numbering: Mapping[str, Collection[tuple[int, bool]]] = field(default_factory=dict)
    facts: BoardFacts | None = None
    lines: Mapping[str, ResolvedLine] = field(default_factory=dict)
    withheld: frozenset[str] = frozenset()
    max_links: int = 3
    # Plain detail level (SPEC_V3 §9.3): evaluations only in words, so a number is a problem.
    words_only_evals: bool = False
    puzzles: PuzzleSettings = field(default_factory=PuzzleSettings)


@dataclass
class Problems:
    invalid: list[str] = field(default_factory=list)  # moves not in the data
    leaks: list[str] = field(default_factory=list)  # moves the player must find
    bare: list[str] = field(default_factory=list)  # notation outside a move tag
    runs: int = 0  # places with more than one move in a row
    misnumbered: list[str] = field(default_factory=list)
    line_leaks: list[str] = field(default_factory=list)  # line links that would reveal
    annotation_leak: bool = False
    evals: list[str] = field(default_factory=list)  # numbers where only words belong (Plain)

    @property
    def leaked(self) -> bool:
        return bool(self.leaks or self.line_leaks or self.annotation_leak)

    @property
    def any(self) -> bool:
        return bool(
            self.invalid or self.bare or self.runs or self.misnumbered or self.leaked or self.evals
        )


@dataclass(frozen=True)
class Processed:
    text: str  # for the player: placeholders for valid tags
    raw: str  # for the coach's history: valid tags as markup
    moves: list[MoveToken]
    line_links: list[LineLink]
    annotations: list[Annotation]
    puzzles: list[PuzzleToken]
    dropped: list[Dropped]  # board-tag shapes, line links and puzzle tags that weren't kept
    removed: list[str]  # moves taken out of the text
    problems: Problems

    @property
    def tokens(self) -> MessageTokens:
        return MessageTokens(
            moves=self.moves,
            line_links=self.line_links,
            annotations=self.annotations,
            puzzles=self.puzzles,
        )


@dataclass
class _Out:
    source: str
    rules: Rules
    text: list[str] = field(default_factory=list)
    raw: list[str] = field(default_factory=list)
    moves: list[MoveToken] = field(default_factory=list)
    links: list[LineLink] = field(default_factory=list)
    annotations: list[Annotation] = field(default_factory=list)
    puzzles: list[PuzzleToken] = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    problems: Problems = field(default_factory=Problems)
    last_move_end: int | None = None  # where the previous move ended, in the source

    @property
    def offset(self) -> int:
        return sum(len(piece) for piece in self.text)

    def plain(self, text: str) -> None:
        self.text.append(text)
        self.raw.append(text)


def process(text: str, rules: Rules) -> Processed:
    out = _Out(source=text, rules=rules)
    last = 0
    for match in _ANY_TAG.finditer(text):
        _plain(last, match.start(), out)
        tag = match.group(0)
        if (move := MOVE_TAG.fullmatch(tag)) is not None:
            _move(_with_number(move["body"], out), match.start(), match.end(), out)
        elif (line := LINE_TAG.fullmatch(tag)) is not None:
            _line(line, out)
        elif (puzzle := PUZZLE_TAG.fullmatch(tag)) is not None:
            _puzzle(puzzle, text[match.end() : match.end() + 1], out)
        elif BOARD_TAG.fullmatch(tag):
            _board(tag, text[match.end() : match.end() + 1], out)
        elif tag.startswith("`") and (inner := MOVE_TAG.search(tag)) is not None:
            # A tag put in code formatting ("`{{move:a4}}`"): the tag counts, the backticks go.
            _move(_with_number(inner["body"], out), match.start(), match.end(), out)
        elif tag.startswith("`"):
            _code(tag, match.start(), match.end(), out)
        else:
            out.dropped.append(Dropped(tag=tag, reason="malformed"))  # an unknown {{...}} tag
        last = match.end()
    _plain(last, len(text), out)
    if rules.words_only_evals:
        _words_only(out)
    return Processed(
        text="".join(out.text),
        raw="".join(out.raw),
        moves=out.moves,
        line_links=out.links,
        annotations=out.annotations,
        puzzles=out.puzzles,
        dropped=out.dropped,
        removed=out.removed,
        problems=out.problems,
    )


def _plain(start: int, end: int, out: _Out) -> None:
    """Text between tags: any notation in it is bare (a problem); in the final text a valid move
    becomes a tag and anything else is removed."""
    segment = out.source[start:end]
    cursor = 0
    for token_start, token_end, token in move_tokens(segment):
        if token not in out.problems.bare:
            out.problems.bare.append(token)
        before = segment[cursor:token_start]
        number = NUMBER_BEFORE.search(before)
        body = token
        if number is not None:
            before = before[: number.start()]
            body = f"{number.group(1)}{_dots(number.group(2))}{token}"
        out.plain(before)
        _move(body, start + token_start, start + token_end, out)
        cursor = token_end
    out.plain(segment[cursor:])


_EVAL = re.compile(
    r"\s?\((?:about |roughly )?[+-]?(?:\d+\.\d|M\d+)\)|(?<![\w.])[+-](?:\d+\.\d|M\d+)\b"
)


def _words_only(out: _Out) -> None:
    """Plain level: evaluation numbers are a problem; in parentheses they're taken out."""
    for i, piece in enumerate(out.text):
        if "(cc:" in piece:
            continue  # a placeholder, not prose
        found = _EVAL.findall(piece)
        if not found:
            continue
        out.problems.evals += [f.strip() for f in found if f.strip() not in out.problems.evals]
        cleaned = re.sub(r"\s?\((?:about |roughly )?[+-]?(?:\d+\.\d|M\d+)\)", "", piece)
        out.text[i] = cleaned
        out.raw[i] = cleaned


def _code(span: str, start: int, end: int, out: _Out) -> None:
    """Inline code: a move written there is bare notation; anything else stays as it is."""
    code = _CODE_MOVE.match(span)
    san = code[2].rstrip("!?") if code else ""
    if code is None or not FULL_SAN.fullmatch(san):
        out.plain(span)
        return
    if san not in out.problems.bare:
        out.problems.bare.append(san)
    _move(code[1].replace(" ", ""), start, end, out)


def _dots(written: str) -> str:
    return "." if written == "." else "..."


def _with_number(body: str, out: _Out) -> str:
    """A move number written just before the tag ("14. {{move:Nf3}}") goes into the tag."""
    if _NUMBERED.match(body) or not out.text:
        return body
    number = NUMBER_BEFORE.search(out.text[-1])
    if number is None:
        return body
    out.text[-1] = out.raw[-1] = out.text[-1][: number.start()]
    return f"{number.group(1)}{_dots(number.group(2))}{body}"


def _move(body: str, start: int, end: int, out: _Out) -> None:
    gap = out.source[out.last_move_end : start] if out.last_move_end is not None else None
    if gap is not None and _RUN_GAP.match(gap):
        out.problems.runs += 1
    out.last_move_end = end

    rules = out.rules
    numbered = _NUMBERED.match(body)
    san = (numbered["san"] if numbered else body).rstrip("!?")
    number = int(numbered["number"]) if numbered else None
    white = numbered["dots"] == "." if numbered else None
    try:
        words = san_words(san)
    except ValueError:
        _remove(san, out, out.problems.invalid)
        return
    key = normalize(san)
    if key in rules.banned and not _other_move(number, white, rules):
        _remove(san, out, out.problems.leaks)
    elif key not in rules.allowed:
        _remove(san, out, out.problems.invalid)
    elif _misnumbered(key, number, white, rules):
        _remove(san, out, out.problems.misnumbered)
    else:
        index = len(out.moves)
        before = "".join(out.text).rstrip(" *_")
        out.moves.append(
            MoveToken(
                index=index, char_offset=out.offset, san=san, words=words, move_number=number,
                white=white, sentence_start=not before or before.endswith(_SENTENCE_END),
            )
        )  # fmt: skip
        out.text.append(f"[{words}](cc:move/{index})")
        written = f"{number}{'.' if white else '...'}{san}" if number is not None else san
        out.raw.append(f"{{{{move:{written}}}}}")


def _other_move(number: int | None, white: bool | None, rules: Rules) -> bool:
    """A banned SAN written with another move's number refers to that move, not the answer."""
    if number is None or white is None:
        return False
    return (number, white) != (rules.move_number, rules.white_to_move)


def _misnumbered(key: str, number: int | None, white: bool | None, rules: Rules) -> bool:
    known = rules.numbering.get(key)
    return known is not None and number is not None and (number, bool(white)) not in known


def _remove(san: str, out: _Out, bucket: list[str]) -> None:
    if san not in bucket:
        bucket.append(san)
    if san not in out.removed:
        out.removed.append(san)
    out.plain(REMOVED)


def _line(match: re.Match[str], out: _Out) -> None:
    rules = out.rules
    ref = match["ref"].strip().lower()
    label = _label(_LABEL_UNSAFE.sub("", match["label"]).strip(), out)
    tag = match.group(0)
    resolved = rules.lines.get(ref)
    if ref in rules.withheld:
        out.problems.line_leaks.append(ref)
        out.dropped.append(Dropped(tag=tag, reason="moment_leak"))
    elif not _REF.match(ref) or resolved is None:
        out.dropped.append(Dropped(tag=tag, reason="unknown_line"))
    elif len(out.links) >= rules.max_links:
        out.dropped.append(Dropped(tag=tag, reason="too_many_links"))
    else:
        index = len(out.links)
        out.links.append(
            LineLink(
                index=index, char_offset=out.offset, line_id=str(uuid.uuid4()), ref=ref,
                label=label, kind=resolved.kind, start_path_uci=list(resolved.start_path_uci),
                moves_uci=list(resolved.moves_uci),
            )
        )  # fmt: skip
        out.text.append(f"[{label}](cc:line/{index})")
        out.raw.append(f"{{{{line:{ref}|{label}}}}}")
        return
    out.plain(label)  # the words stay, as plain text


def _label(label: str, out: _Out) -> str:
    """A link's words can't hold notation either: a move there is bare (regenerate once); in the
    final text a valid one is shown in words and anything else is left out."""
    pieces, last = [], 0
    for start, end, token in move_tokens(label):
        if token not in out.problems.bare:
            out.problems.bare.append(token)
        key = normalize(token)
        allowed = key in out.rules.allowed and key not in out.rules.banned
        pieces.append(label[last:start])
        pieces.append(san_words(token) if allowed else "")
        if not allowed and token not in out.removed:
            out.removed.append(token)
        last = end
    pieces.append(label[last:])
    return " ".join("".join(pieces).split())


def _puzzle(match: re.Match[str], after: str, out: _Out) -> None:
    """Only themes from the allowed list (SPEC_V3 §8.2); anything else is dropped and logged."""
    wanted = match["theme"].strip()
    themes = out.rules.puzzles.themes
    slug = next((s for s in themes if s.lower() == wanted.lower()), None)
    if slug is None:
        out.dropped.append(Dropped(tag=match.group(0), reason="unknown_puzzle"))
        if out.text:
            out.text[-1] = out.raw[-1] = trim_before(out.text[-1], after)
        return
    index = len(out.puzzles)
    url = out.rules.puzzles.url.format(slug=slug)
    out.puzzles.append(
        PuzzleToken(index=index, char_offset=out.offset, theme=slug, label=themes[slug], url=url)
    )
    out.text.append(f"[{themes[slug]}](cc:puzzle/{index})")
    out.raw.append(f"{{{{puzzle:{slug}}}}}")


def _board(tag: str, after: str, out: _Out) -> None:
    rules = out.rules
    arrows, squares = check_tag(tag, rules.facts, rules.limits, len(out.annotations), out.dropped)
    if any(d.reason == "moment_leak" and d.tag == tag for d in out.dropped):
        out.problems.annotation_leak = True
    if not arrows and not squares:
        if out.text:
            out.text[-1] = out.raw[-1] = trim_before(out.text[-1], after)
        return
    index = len(out.annotations)
    out.annotations.append(
        Annotation(tag_index=index, char_offset=out.offset, arrows=arrows, squares=squares)
    )
    out.text.append(f"[board](cc:board/{index})")
    out.raw.append(serialize(arrows, squares))


def note(problems: Problems) -> str:
    """What to fix, for the one regeneration. Never names a move the player must find."""
    parts = []
    if problems.leaked:
        parts.append(
            "Your answer named, linked to or pointed out a move the player is supposed to find "
            "for themselves. Don't name any move for the player to play, say where a piece should "
            "go, link to its line, or mark its squares."
        )
    if problems.invalid:
        parts.append(f"These moves are not in the data: {', '.join(problems.invalid)}.")
    if problems.misnumbered:
        parts.append(f"These moves have the wrong move number: {', '.join(problems.misnumbered)}.")
    if problems.bare:
        shown = [move for move in problems.bare if move not in problems.leaks]  # never the answer
        wrote = f" (you wrote: {', '.join(shown)})" if shown else ""
        parts.append(
            # The example names no real move: any real one could be the answer to a moment.
            "Write every move as a move tag, {{move:SAN}} with the move as the data writes it, "
            f"never as plain notation in the text{wrote}."
        )
    if problems.evals:
        parts.append(
            "The player's detail level is plain: describe evaluations only in words, never as "
            f"numbers (you wrote: {', '.join(problems.evals)})."
        )
    if problems.runs:
        parts.append(
            "Never write more than one move in a row: describe the idea, and if a sequence "
            "matters, link to its line with a line link."
        )
    parts.append("Rewrite the complete answer.")
    return " ".join(parts)
