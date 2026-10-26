"""Fake engine output for tests: legal lines from python-chess, with chosen White-POV evals."""

from typing import Any

import chess


def legal_line(fen: str, plies: int) -> list[str]:
    """A deterministic legal line: always the first legal move in UCI order."""
    board = chess.Board(fen)
    moves = []
    for _ in range(plies):
        legal = sorted(board.legal_moves, key=lambda m: m.uci())
        if not legal:
            break
        moves.append(legal[0].uci())
        board.push(legal[0])
    return moves


def fake_result(
    fen: str,
    tier: str,
    *,
    cp: int | None = 0,
    mate: int | None = None,
    lines: int = 1,
    plies: int = 3,
    depth: int = 20,
    time_ms: int = 300,
) -> dict[str, Any]:
    board = chess.Board(fen)
    first_moves = sorted(board.legal_moves, key=lambda m: m.uci())[:lines]
    result_lines = []
    for rank, move in enumerate(first_moves, start=1):
        board.push(move)
        rest = legal_line(board.fen(), plies - 1)
        board.pop()
        result_lines.append(
            {
                "rank": rank,
                "eval_cp": cp if mate is None else None,
                "mate": mate,
                "moves_uci": [move.uci(), *rest],
            }
        )
    return {
        "ply": None,
        "fen": fen,
        "tier": tier,
        "depth": depth,
        "time_ms": time_ms,
        "lines": result_lines,
    }
