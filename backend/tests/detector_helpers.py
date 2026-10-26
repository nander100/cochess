"""Builders for detector tests: a MoveContext from a FEN and SAN moves, or a GameContext from a
PGN with chosen per-position evals."""

from collections.abc import Sequence

import chess

from app.analysis.classify import Classification
from app.analysis.detectors.types import GameContext, MoveContext
from app.analysis.engine import EngineResult
from app.analysis.evals import Color, Evaluation
from app.analysis.moves import build_game_context
from app.analysis.pgn import parse_pgn
from app.analysis.phase import Phase, game_phase
from app.analysis.selection import scan_fens
from app.config import DetectorSettings, Settings
from tests.engine_fakes import fake_result

DETECTOR_SETTINGS = DetectorSettings()


def san_line(board: chess.Board, sans: Sequence[str]) -> tuple[chess.Move, ...]:
    work = board.copy()
    moves = []
    for san in sans:
        move = work.parse_san(san)
        moves.append(move)
        work.push(move)
    return tuple(moves)


def move_ctx(
    fen: str,
    san: str,
    *,
    best_before: Sequence[str] = (),
    best_after: Sequence[str] = (),
    classification: Classification | None = "mistake",
    missed_mate: bool = False,
    eval_before: Evaluation | None = None,
    eval_after: Evaluation | None = None,
    phase: Phase | None = None,
    clock_s: float | None = None,
) -> MoveContext:
    before = chess.Board(fen)
    move = before.parse_san(san)
    after = before.copy()
    after.push(move)
    color: Color = "white" if before.turn == chess.WHITE else "black"
    ply = before.fullmove_number * 2 - (1 if color == "white" else 0)
    return MoveContext(
        ply=ply,
        move_number=before.fullmove_number,
        color=color,
        move=move,
        san=before.san(move),
        board_before=before,
        board_after=after,
        classification=classification,
        missed_mate=missed_mate,
        drop=0.3,
        eval_before=eval_before or Evaluation(cp=0),
        eval_after=eval_after or Evaluation(cp=-300),
        best_line_before=san_line(before, best_before),
        best_line_after=san_line(after, best_after),
        phase=phase or game_phase(before, ply, DETECTOR_SETTINGS),
        clock_s=clock_s,
        settings=DETECTOR_SETTINGS,
    )


def game_ctx(pgn: str, user_color: Color, cps: Sequence[int] | None = None) -> GameContext:
    """`cps[i]` is the White-POV eval of the position before ply i + 1; the last is the final."""
    settings = Settings(_env_file=None)
    game = parse_pgn(pgn, max_chars=100_000, max_plies=600)
    fens = [p.fen_before for p in game.positions] + [game.final_fen]
    values = list(cps) if cps is not None else [0] * len(fens)
    by_fen = dict(zip(fens, values, strict=True))
    results = [
        EngineResult.model_validate(fake_result(fen, "scan", cp=by_fen[fen]))
        for fen in scan_fens(game)
    ]
    return build_game_context(game, results, user_color, settings)
