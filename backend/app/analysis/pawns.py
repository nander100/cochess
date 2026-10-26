"""Pawn-structure features: doubled, isolated, backward and passed pawns."""

import chess


def _pawns(board: chess.Board, color: chess.Color) -> chess.SquareSet:
    return board.pieces(chess.PAWN, color)


def _file_counts(board: chess.Board, color: chess.Color) -> list[int]:
    counts = [0] * 8
    for square in _pawns(board, color):
        counts[chess.square_file(square)] += 1
    return counts


def _ahead(rank: int, other_rank: int, color: chess.Color) -> bool:
    return other_rank > rank if color == chess.WHITE else other_rank < rank


def doubled_files(board: chess.Board, color: chess.Color) -> frozenset[str]:
    return frozenset(chess.FILE_NAMES[f] for f, n in enumerate(_file_counts(board, color)) if n > 1)


def isolated_files(board: chess.Board, color: chess.Color) -> frozenset[str]:
    counts = _file_counts(board, color)
    return frozenset(
        chess.FILE_NAMES[f]
        for f in range(8)
        if counts[f] and not any(counts[g] for g in (f - 1, f + 1) if 0 <= g < 8)
    )


def passed_pawns(board: chess.Board, color: chess.Color) -> frozenset[chess.Square]:
    """Pawns with no enemy pawn ahead of them on their own or an adjacent file."""
    enemies = _pawns(board, not color)
    passed = set()
    for square in _pawns(board, color):
        file, rank = chess.square_file(square), chess.square_rank(square)
        if not any(
            abs(chess.square_file(e) - file) <= 1 and _ahead(rank, chess.square_rank(e), color)
            for e in enemies
        ):
            passed.add(square)
    return frozenset(passed)


def backward_pawns(board: chess.Board, color: chess.Color) -> frozenset[chess.Square]:
    """Pawns no friendly pawn can support, whose advance square is covered by an enemy pawn."""
    friends = _pawns(board, color)
    step = 8 if color == chess.WHITE else -8
    backward = set()
    for square in friends:
        file, rank = chess.square_file(square), chess.square_rank(square)
        supported = any(
            abs(chess.square_file(f) - file) == 1 and not _ahead(rank, chess.square_rank(f), color)
            for f in friends
        )
        stop = square + step
        if supported or not 0 <= stop < 64:
            continue
        if board.attackers(not color, stop) & _pawns(board, not color):
            backward.add(square)
    return frozenset(backward)
