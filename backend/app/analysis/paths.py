"""Board positions sent by the browser as UCI paths (SPEC_V2 §5.2), replayed with python-chess.

The frontend only ever sends the moves from the start position; the FEN, SAN, and whether the
position is in the game or in a variation the player is exploring all come from here.
"""

from collections.abc import Sequence

import chess
from pydantic import BaseModel, ConfigDict

from app.analysis.pgn import ParsedGame


class PathError(Exception):
    """The path isn't a legal sequence of moves. `message` is safe to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ResolvedPath(BaseModel):
    """A position on the board, as the coach payload describes it (SPEC_V2 §6.1)."""

    model_config = ConfigDict(frozen=True)

    path_uci: list[str]
    path_san: list[str]
    fen: str
    ply: int  # moves played to reach the position; 0 = the start
    on_mainline: bool
    # Where the player left the game: the ply of the first move that differs. None on the mainline.
    branch_ply: int | None
    variation_san: list[str]  # the moves since leaving the game
    pgn_to_move: str  # "1. d4 d5 2. Bf4 ..."


def resolve_path(game: ParsedGame, path_uci: Sequence[str], max_plies: int) -> ResolvedPath:
    if len(path_uci) > max_plies:
        raise PathError(f"That position is too deep (limit {max_plies} moves).")
    board = chess.Board()
    sans: list[str] = []
    for index, uci in enumerate(path_uci):
        try:
            move = chess.Move.from_uci(uci)
        except chess.InvalidMoveError as error:
            raise PathError(f"Move {index + 1} of the position isn't a valid move.") from error
        if move not in board.legal_moves:
            raise PathError(f"Move {index + 1} of the position ({uci}) isn't legal there.")
        sans.append(board.san(move))
        board.push(move)

    mainline = [p.uci for p in game.positions]
    shared = _shared_prefix(mainline, path_uci)
    on_mainline = shared == len(path_uci)
    return ResolvedPath(
        path_uci=list(path_uci),
        path_san=sans,
        fen=board.fen(),
        ply=len(path_uci),
        on_mainline=on_mainline,
        branch_ply=None if on_mainline else shared + 1,
        variation_san=[] if on_mainline else sans[shared:],
        pgn_to_move=movetext(sans),
    )


def position_key(fen: str) -> str:
    """A position's identity: the FEN without the move counters (placement, side, castling,
    en passant), so transpositions in variations match stored results."""
    return " ".join(fen.split()[:4])


def movetext(sans: Sequence[str], first_ply: int = 1) -> str:
    """Numbered SAN: "1. d4 d5 2. Bf4", or "2... d5 3. Bf4" when it starts with Black."""
    parts = []
    for index, san in enumerate(sans):
        ply = first_ply + index
        number = (ply + 1) // 2
        if ply % 2 == 1:
            parts.append(f"{number}. {san}")
        else:
            parts.append(f"{number}... {san}" if index == 0 else san)
    return " ".join(parts)


def _shared_prefix(mainline: Sequence[str], path: Sequence[str]) -> int:
    shared = 0
    for game_move, path_move in zip(mainline, path, strict=False):
        if game_move != path_move:
            break
        shared += 1
    return shared
