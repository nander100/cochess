"""Builds the game summary (SPEC §6.5) from a parsed game and its engine results."""

from collections.abc import Sequence

from app.analysis.accuracy import MoveAccuracy, aggregate, move_accuracies
from app.analysis.detectors import run_detectors
from app.analysis.detectors.types import GameContext, MoveContext, ThemeFact
from app.analysis.engine import EngineResult, best_by_fen, uci_line_to_san
from app.analysis.evals import format_eval, win_percent, winning_chances
from app.analysis.material import line_to_san
from app.analysis.moves import build_game_context
from app.analysis.pgn import ParsedGame
from app.analysis.phase import PHASES, Phase
from app.analysis.summary_models import (
    Accuracy,
    Counts,
    EvalPoint,
    GameInfo,
    GameSummary,
    KeyMoment,
    LineSummary,
    MoveEntry,
    MoveLabel,
    PhaseStats,
    UserInfo,
)
from app.config import Settings

# Key moments come in this order before the biggest swings are added (PLAN Q19).
_MOMENT_PRIORITY: dict[MoveLabel, int] = {"missed_mate": 0, "blunder": 1, "mistake": 2}


def build_summary(
    game: ParsedGame, results: Sequence[EngineResult], user: UserInfo, settings: Settings
) -> GameSummary:
    context = build_game_context(game, results, user.color, settings)
    facts = run_detectors(context)
    accuracies = move_accuracies(
        [win_percent(m.eval_before) for m in context.moves]
        + [win_percent(context.moves[-1].eval_after)]
    )
    user_moves = context.user_moves()
    return GameSummary(
        game=_game_info(game),
        user=user,
        accuracy=Accuracy(
            user=_rounded(aggregate([a for a in accuracies if a.color == user.color])),
            opponent=_rounded(aggregate([a for a in accuracies if a.color != user.color])),
        ),
        counts=Counts(
            inaccuracies=_count(user_moves, "inaccuracy"),
            mistakes=_count(user_moves, "mistake"),
            blunders=_count(user_moves, "blunder"),
            missed_mates=sum(m.missed_mate for m in user_moves),
        ),
        phase_breakdown=_phase_breakdown(user_moves, accuracies),
        eval_curve=[EvalPoint(ply=m.ply, eval=format_eval(m.eval_after)) for m in context.moves],
        key_moments=_key_moments(context, results, facts, settings),
        theme_facts=facts,
        move_list=[
            MoveEntry(
                ply=m.ply,
                move_number=m.move_number,
                side=m.color,
                san=m.san,
                eval_after=format_eval(m.eval_after),
                classification=label(m),
            )
            for m in context.moves
        ],
    )


def label(move: MoveContext) -> MoveLabel | None:
    if move.missed_mate and move.classification != "blunder":
        return "missed_mate"
    return move.classification


def _game_info(game: ParsedGame) -> GameInfo:
    headers = game.headers
    opening = headers.get("Opening") or (f"ECO {headers['ECO']}" if headers.get("ECO") else None)
    return GameInfo(
        white=headers.get("White", "?"),
        black=headers.get("Black", "?"),
        result=headers.get("Result", "*"),
        time_control=headers.get("TimeControl"),
        opening=opening,
        num_moves=(game.positions[-1].ply + 1) // 2,
    )


def _count(moves: Sequence[MoveContext], classification: str) -> int:
    return sum(m.classification == classification for m in moves)


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _phase_breakdown(
    user_moves: Sequence[MoveContext], accuracies: Sequence[MoveAccuracy]
) -> dict[Phase, PhaseStats]:
    by_ply = {a.ply: a for a in accuracies}
    breakdown: dict[Phase, PhaseStats] = {}
    for phase in PHASES:
        moves = [m for m in user_moves if m.phase == phase]
        breakdown[phase] = PhaseStats(
            moves=len(moves),
            accuracy=_rounded(aggregate([by_ply[m.ply] for m in moves])),
            inaccuracies=_count(moves, "inaccuracy"),
            mistakes=_count(moves, "mistake"),
            blunders=_count(moves, "blunder"),
        )
    return breakdown


def _key_moments(
    context: GameContext,
    results: Sequence[EngineResult],
    facts: Sequence[ThemeFact],
    settings: Settings,
) -> list[KeyMoment]:
    """The user's mistakes, blunders and missed mates, then the biggest swings by either side."""
    limit, swings = settings.thresholds.key_moments_max, settings.thresholds.key_moment_swings
    errors = [m for m in context.user_moves() if label(m) in _MOMENT_PRIORITY]
    chosen = sorted(errors, key=lambda m: (_MOMENT_PRIORITY[label(m) or "mistake"], -m.drop))
    by_swing = sorted(context.moves, key=lambda m: (-_swing(m), m.ply))
    chosen_plies = {m.ply for m in chosen}
    chosen += [m for m in by_swing[:swings] if m.ply not in chosen_plies]

    by_fen = best_by_fen(results)
    moments = []
    for move in sorted(chosen[:limit], key=lambda m: m.ply):
        fen = move.board_before.fen()
        result = by_fen.get(fen)
        lines = [
            LineSummary(
                rank=line.rank,
                eval=format_eval(line.evaluation()),
                moves_san=uci_line_to_san(fen, line.moves_uci),
            )
            for line in (result.lines if result else [])
        ]
        moments.append(
            KeyMoment(
                ply=move.ply,
                move_number=move.move_number,
                side=move.color,
                move_san=move.san,
                classification=label(move),
                eval_before=format_eval(move.eval_before),
                eval_after=format_eval(move.eval_after),
                best_move_san=lines[0].moves_san[0] if lines else None,
                engine_lines=lines,
                line_after_san=line_to_san(move.board_after, move.best_line_after),
                themes=sorted({f.theme for f in facts if f.ply == move.ply}),
            )
        )
    return moments


def _swing(move: MoveContext) -> float:
    return abs(winning_chances(move.eval_after) - winning_chances(move.eval_before))
