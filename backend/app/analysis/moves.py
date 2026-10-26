"""Turns a parsed game plus engine results into per-ply contexts for the detectors."""

from collections.abc import Sequence

import chess

from app.analysis.classify import classify, is_missed_mate
from app.analysis.detectors.types import GameContext, MoveContext
from app.analysis.engine import EngineResult, best_by_fen, position_evaluations
from app.analysis.evals import Color, for_color, winning_chances
from app.analysis.pgn import ParsedGame
from app.analysis.phase import game_phase
from app.config import Settings


def build_game_context(
    game: ParsedGame, results: Sequence[EngineResult], user_color: Color, settings: Settings
) -> GameContext:
    """Every ply with its evals (verified where available), classification and engine lines.

    Both sides' moves are classified (needed for opponent accuracy, PLAN Q20); per-move
    detectors only run on the user's.
    """
    by_fen = best_by_fen(results)
    evals = position_evaluations(game, by_fen)
    board = chess.Board()
    moves = []
    for index, position in enumerate(game.positions):
        before = board.copy(stack=False)
        move = chess.Move.from_uci(position.uci)
        board.push(move)
        after = board.copy(stack=False)
        mover: Color = "white" if position.ply % 2 == 1 else "black"
        eval_before, eval_after = evals[index], evals[index + 1]
        drop = for_color(winning_chances(eval_before) - winning_chances(eval_after), mover)
        moves.append(
            MoveContext(
                ply=position.ply,
                move_number=(position.ply + 1) // 2,
                color=mover,
                move=move,
                san=position.san,
                board_before=before,
                board_after=after,
                classification=classify(drop, settings.thresholds),
                missed_mate=is_missed_mate(eval_before, eval_after, mover, settings.thresholds),
                drop=drop,
                eval_before=eval_before,
                eval_after=eval_after,
                best_line_before=_best_line(by_fen, before.fen()),
                best_line_after=_best_line(by_fen, after.fen()),
                phase=game_phase(before, position.ply, settings.detectors),
                clock_s=position.clock_s,
                settings=settings.detectors,
            )
        )
    return GameContext(
        user_color=user_color,
        moves=tuple(moves),
        headers=game.headers,
        final_board=board,
        settings=settings.detectors,
    )


def _best_line(by_fen: dict[str, EngineResult], fen: str) -> tuple[chess.Move, ...]:
    result = by_fen.get(fen)
    if result is None:  # a terminal final position has no engine result
        return ()
    return tuple(chess.Move.from_uci(uci) for uci in result.lines[0].moves_uci)
