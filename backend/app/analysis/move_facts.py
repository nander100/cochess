"""Facts about each step of a line, for walkthroughs (SPEC_V3 §7.2 step 3).

Pure functions on python-chess boards: what moved, what it took, whether it checks, which enemy
pieces it newly attacks while they're loose, which of the mover's own pieces it leaves loose,
the material balance, and the engine's evaluation after the move (from the browser's per-step
scan, already checked by the backend). The coach explains these; it never works them out.
"""

from collections.abc import Sequence

import chess
from pydantic import BaseModel

from app.analysis.evals import Color, Evaluation, format_eval
from app.analysis.material import balance, is_loose

PIECE_NAMES: dict[chess.PieceType, str] = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


class StepFacts(BaseModel):
    index: int  # 1-based step in the line
    move_number: int
    side: Color
    san: str
    piece: str  # "knight"
    from_square: str
    to_square: str
    captured: str | None  # "pawn", or None
    check: bool
    checkmate: bool
    # Enemy pieces the move leaves attacked and loose (undefended, or attacked by a cheaper
    # piece) that weren't before: "rook on a8".
    newly_attacked: list[str]
    # The mover's own pieces that are loose after the move and weren't before (the moved piece
    # counts if it landed en prise).
    left_hanging: list[str]
    material: int  # White's material minus Black's after the move, in pawns
    eval_after: str | None  # "+0.8", "-M2"; None when the step wasn't evaluated
    eval_change: str | None  # White POV, centipawn evals only: "+0.5"


def step_facts(
    start_fen: str, line_uci: Sequence[str], evals: Sequence[Evaluation | None]
) -> list[StepFacts]:
    """`evals[0]` is the start position's evaluation, `evals[i]` the one after move i (None when
    unknown). Raises ValueError on an illegal move: callers replay the line first."""
    if len(evals) != len(line_uci) + 1:
        raise ValueError("one evaluation per position: the start and after each move")
    board = chess.Board(start_fen)
    facts = []
    for index, uci in enumerate(line_uci, start=1):
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"{uci} is not legal in {board.fen()}")
        facts.append(_step(board, move, index, evals[index - 1], evals[index]))
        board.push(move)
    return facts


def _step(
    board: chess.Board,
    move: chess.Move,
    index: int,
    before_eval: Evaluation | None,
    after_eval: Evaluation | None,
) -> StepFacts:
    mover = board.turn
    piece = board.piece_at(move.from_square)
    assert piece is not None
    captured = _captured(board, move)
    after = board.copy(stack=False)
    after.push(move)
    return StepFacts(
        index=index,
        move_number=board.fullmove_number,
        side="white" if mover == chess.WHITE else "black",
        san=board.san(move),
        piece=PIECE_NAMES[piece.piece_type],
        from_square=chess.square_name(move.from_square),
        to_square=chess.square_name(move.to_square),
        captured=PIECE_NAMES[captured] if captured is not None else None,
        check=after.is_check(),
        checkmate=after.is_checkmate(),
        newly_attacked=_named(after, _loose(after, not mover) - _loose(board, not mover)),
        left_hanging=_named(after, _loose(after, mover) - _loose(board, mover)),
        material=balance(after, chess.WHITE),
        eval_after=format_eval(after_eval) if after_eval is not None else None,
        eval_change=_change(before_eval, after_eval),
    )


def _captured(board: chess.Board, move: chess.Move) -> chess.PieceType | None:
    if board.is_en_passant(move):
        return chess.PAWN
    return board.piece_type_at(move.to_square) if board.is_capture(move) else None


def _loose(board: chess.Board, color: chess.Color) -> set[chess.Square]:
    """`color`'s pieces (kings aside) that are loose in `board`."""
    return {
        square
        for square, piece in board.piece_map().items()
        if piece.color == color and piece.piece_type != chess.KING and is_loose(board, square)
    }


def _named(board: chess.Board, squares: set[chess.Square]) -> list[str]:
    names = []
    for square in sorted(squares):
        piece = board.piece_at(square)
        assert piece is not None
        names.append(f"{PIECE_NAMES[piece.piece_type]} on {chess.square_name(square)}")
    return names


def _change(before: Evaluation | None, after: Evaluation | None) -> str | None:
    if before is None or after is None or before.cp is None or after.cp is None:
        return None
    return f"{(after.cp - before.cp) / 100:+.1f}"
