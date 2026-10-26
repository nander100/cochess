"""PGN parsing and validation (SPEC §9.2). python-chess is the single source of truth."""

import io
import re
from typing import Literal

import chess
import chess.pgn
from pydantic import BaseModel, ConfigDict

PgnErrorCode = Literal[
    "too_large",
    "no_moves",
    "illegal_move",
    "non_standard_start",
    "unsupported_variant",
    "multiple_games",
    "too_long",
]

_STANDARD_VARIANT = "standard"
_SAN_IN_ERROR = re.compile(r"san: '([^']*)'")
_NO_MOVES_MESSAGE = "No moves found. Paste a PGN that contains the game's moves."


class PgnError(Exception):
    """The submitted PGN can't be analyzed. `message` is written to be shown to the user."""

    def __init__(self, code: PgnErrorCode, message: str, move_number: int | None = None) -> None:
        super().__init__(message)
        self.code: PgnErrorCode = code
        self.message = message
        self.move_number = move_number


class Position(BaseModel):
    """The position before the move at `ply`, and that move."""

    model_config = ConfigDict(frozen=True)

    ply: int
    fen_before: str
    san: str
    uci: str
    clock_s: float | None


class ParsedGame(BaseModel):
    model_config = ConfigDict(frozen=True)

    headers: dict[str, str]
    positions: tuple[Position, ...]
    final_fen: str
    final_is_terminal: bool  # checkmate or stalemate: no engine search needed (or possible)
    pgn: str  # main line only; %clk kept, all other comments, NAGs and variations removed


class _GameBuilder(chess.pgn.GameBuilder[chess.pgn.Game]):
    """Builds the main line only, so every recorded error is a main-line error. Doesn't log.

    Skipping variations (rather than parsing then discarding them) also sidesteps python-chess's
    recovery after an error inside a variation, which resumes the main line on the wrong board.
    """

    # BaseVisitor (what read_game calls) allows SKIP here; GameBuilder's stub narrows it to None.
    def begin_variation(self) -> chess.pgn.SkipType:  # type: ignore[override]
        return chess.pgn.SKIP

    def end_variation(self) -> None:
        pass  # Nothing was pushed in begin_variation.

    def handle_error(self, error: Exception) -> None:
        self.game.errors.append(error)


def parse_pgn(text: str, *, max_chars: int, max_plies: int) -> ParsedGame:
    """Parse exactly one standard-chess game. Raises PgnError with a user-facing message."""
    if len(text) > max_chars:
        raise PgnError("too_large", f"That PGN is too long (limit {max_chars:,} characters).")

    handle = io.StringIO(text)
    game = chess.pgn.read_game(handle, Visitor=_GameBuilder)
    if game is None:
        raise PgnError("no_moves", _NO_MOVES_MESSAGE)

    _reject_extra_games(handle)
    _check_start_position(game)
    if game.errors:
        raise _move_error(game, game.errors[0])

    nodes = list(game.mainline())
    if not nodes:
        raise PgnError("no_moves", _NO_MOVES_MESSAGE)
    if len(nodes) > max_plies:
        raise PgnError("too_long", f"That game is too long to analyze (limit {max_plies} plies).")

    board = game.board()
    positions = []
    for ply, node in enumerate(nodes, start=1):
        if not node.move:  # "--", "Z0" and "0000" parse as null moves
            move_number, side = _move_label(ply)
            raise PgnError(
                "illegal_move",
                f"Move {move_number} ({side}): null moves (--) aren't allowed.",
                move_number,
            )
        positions.append(
            Position(
                ply=ply,
                fen_before=board.fen(),
                san=board.san(node.move),
                uci=node.move.uci(),
                clock_s=node.clock(),
            )
        )
        board.push(node.move)

    return ParsedGame(
        headers=dict(game.headers),
        positions=tuple(positions),
        final_fen=board.fen(),
        final_is_terminal=board.is_checkmate() or board.is_stalemate(),
        pgn=_export_mainline(game),
    )


def _reject_extra_games(handle: io.StringIO) -> None:
    extra = chess.pgn.read_game(handle, Visitor=_GameBuilder)
    if extra is None:
        return
    has_moves = extra.next() is not None
    has_own_headers = dict(extra.headers) != dict(chess.pgn.Game().headers)
    if has_moves or has_own_headers:
        raise PgnError("multiple_games", "Please paste one game at a time.")


def _check_start_position(game: chess.pgn.Game) -> None:
    variant = game.headers.get("Variant")
    if variant is not None and variant.strip().lower() != _STANDARD_VARIANT:
        raise PgnError(
            "unsupported_variant", f"Only standard chess is supported (this game is {variant})."
        )
    if game.board().epd() != chess.Board().epd():
        raise PgnError("non_standard_start", "Non-standard starting positions aren't supported.")


def _move_error(game: chess.pgn.Game, error: Exception) -> PgnError:
    # python-chess stops the main line at the bad move, so it's the ply after the last good one.
    move_number, side = _move_label(sum(1 for _ in game.mainline_moves()) + 1)
    match = _SAN_IN_ERROR.search(str(error))
    san = match.group(1) if match else "the move"

    if isinstance(error, chess.AmbiguousMoveError):
        problem = f"{san} is ambiguous (more than one piece can make that move)"
    elif isinstance(error, chess.IllegalMoveError):
        problem = f"{san} is not a legal move in that position"
    else:
        problem = f"{san} isn't a valid move"
    return PgnError("illegal_move", f"Move {move_number} ({side}): {problem}.", move_number)


def _move_label(ply: int) -> tuple[int, str]:
    return (ply + 1) // 2, "White" if ply % 2 == 1 else "Black"


def _export_mainline(game: chess.pgn.Game) -> str:
    clean = chess.pgn.Game(headers=game.headers)
    node: chess.pgn.GameNode = clean
    for source in game.mainline():
        node = node.add_main_variation(source.move)
        clock = source.clock()
        if clock is not None:
            node.set_clock(clock)
    return str(clean)
