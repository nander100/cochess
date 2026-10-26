"""slow_development (SPEC §6.4 #4, game-level): minor pieces still home at move 10, or no
castling by move 12 with queens on. Raised to "concern" if the opening cost >= 0.15 wc."""

from typing import Literal

import chess

from app.analysis.detectors.types import GameContext, MoveContext, ThemeFact, game_fact
from app.analysis.evals import for_color, winning_chances
from app.config import DetectorSettings

_N, _B = chess.KNIGHT, chess.BISHOP
_HOME_MINORS: dict[chess.Color, dict[chess.Square, chess.PieceType]] = {
    chess.WHITE: {chess.B1: _N, chess.G1: _N, chess.C1: _B, chess.F1: _B},
    chess.BLACK: {chess.B8: _N, chess.G8: _N, chess.C8: _B, chess.F8: _B},
}


def detect(game: GameContext) -> list[ThemeFact]:
    settings, moves = game.settings, game.user_moves()
    if len(moves) < settings.development_move:
        return []
    user = moves[0].side
    board = moves[settings.development_move - 1].board_after
    undeveloped = [
        f"{chess.piece_name(kind)} {chess.square_name(square)}"
        for square, kind in _HOME_MINORS[user].items()
        if board.piece_at(square) == chess.Piece(kind, user)
    ]
    castle = next((m for m in moves if m.board_before.is_castling(m.move)), None)
    late = _castled_late(moves, castle, settings)
    if len(undeveloped) < settings.min_undeveloped_minors and not late:
        return []

    lost = _opening_wc_lost(game)
    severity: Literal["note", "concern"] = (
        "concern" if lost >= settings.opening_wc_loss_for_concern else "note"
    )
    side = None
    if castle is not None:
        kingside = castle.board_before.is_kingside_castling(castle.move)
        side = "kingside" if kingside else "queenside"
    return [
        game_fact(
            "slow_development",
            severity,
            {
                "undeveloped_at_move": settings.development_move,
                "undeveloped": undeveloped,
                "castled": castle is not None,
                "castle_side": side,
                "castled_move": castle.move_number if castle else None,
                "not_castled_by_move": settings.castle_by_move if late else None,
                "opening_wc_lost": round(lost, 2),
            },
        )
    ]


def _castled_late(
    moves: tuple[MoveContext, ...], castle: MoveContext | None, settings: DetectorSettings
) -> bool:
    if castle is not None and castle.move_number <= settings.castle_by_move:
        return False
    if len(moves) < settings.castle_by_move:
        return False
    board = moves[settings.castle_by_move - 1].board_after
    return all(board.pieces(chess.QUEEN, color) for color in chess.COLORS)


def _opening_wc_lost(game: GameContext) -> float:
    """The user's net winning-chances loss from the first position to the end of the opening."""
    opening = [m for m in game.moves if m.phase == "opening"]
    if not opening:
        return 0.0
    start = for_color(winning_chances(game.moves[0].eval_before), game.user_color)
    end = for_color(winning_chances(opening[-1].eval_after), game.user_color)
    return max(0.0, start - end)
