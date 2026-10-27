"""Builds GET /api/games/{id}: the stored game and its analysis, as the analysis board shows it."""

from collections.abc import Mapping, Sequence
from typing import cast

from sqlalchemy.orm import Session

from app.analysis.engine import EngineResult, best_by_fen, position_evaluations, uci_line_to_san
from app.analysis.evals import Color, Evaluation, format_eval, win_percent
from app.analysis.pgn import ParsedGame, parse_pgn
from app.analysis.selection import select_verify_plies, verify_fens
from app.analysis.summary import game_info
from app.api.schemas import (
    GameDetail,
    GameStatus,
    MoveInfo,
    StoredEngineResult,
    StoredLine,
    StoredSynopsis,
)
from app.config import Settings
from app.db.chat import chat_history
from app.db.coach import load_synopsis
from app.db.engine_results import load_results, load_summary
from app.db.models import Game


def build_detail(session: Session, game: Game, settings: Settings) -> GameDetail:
    parsed = parse_pgn(
        game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
    )
    user_color = cast(Color, game.user_color)  # validated on upload
    results = load_results(session, game.id, ["scan", "verify", "deep"])
    evals = _evaluations(parsed, best_by_fen(results))
    summary = load_summary(session, game.id)
    labels = {move.ply: move.classification for move in summary.move_list} if summary else {}
    synopsis = load_synopsis(session, game.id)

    moves = [
        MoveInfo(
            ply=p.ply,
            move_number=(p.ply + 1) // 2,
            side="white" if p.ply % 2 == 1 else "black",
            san=p.san,
            uci=p.uci,
            fen_before=p.fen_before,
            clock_s=p.clock_s,
            eval_after=format_eval(evals[p.ply]) if evals else None,
            win_pct_after=round(win_percent(evals[p.ply]), 1) if evals else None,
            label=labels.get(p.ply),
        )
        for p in parsed.positions
    ]
    status = cast(GameStatus, game.status)
    return GameDetail(
        id=game.id,
        status=status,
        user_color=user_color,
        elo=game.elo,
        played_at=game.played_at or game.created_at,
        info=summary.game if summary else game_info(parsed),
        moves=moves,
        start_win_pct=round(win_percent(evals[0]), 1) if evals else None,
        final_fen=parsed.final_fen,
        final_is_terminal=parsed.final_is_terminal,
        accuracy=summary.accuracy if summary else None,
        counts=summary.counts if summary else None,
        engine_results=[_stored(result) for result in best_by_fen(results).values()],
        verify_fens=_pending_verify(parsed, results, user_color, settings, status),
        synopsis=StoredSynopsis(text=synopsis[0], invalid_moves_removed=synopsis[1])
        if synopsis
        else None,
        chat=chat_history(session, game.id),
    )


def _evaluations(parsed: ParsedGame, by_fen: Mapping[str, EngineResult]) -> list[Evaluation] | None:
    """Every position's evaluation (before each ply, then the final one), or None until the
    scan has covered them all."""
    try:
        return position_evaluations(parsed, dict(by_fen))
    except KeyError:
        return None


def _pending_verify(
    parsed: ParsedGame,
    results: Sequence[EngineResult],
    user_color: Color,
    settings: Settings,
    status: GameStatus,
) -> list[str]:
    """The positions the verify step expects: the same choice POST .../engine/verify makes, from
    the scan results only."""
    if status != "scanned":
        return []
    evals = _evaluations(parsed, best_by_fen([r for r in results if r.tier == "scan"]))
    if evals is None:
        return []
    return verify_fens(parsed, select_verify_plies(evals, user_color, settings.thresholds))


def _stored(result: EngineResult) -> StoredEngineResult:
    return StoredEngineResult(
        fen=result.fen,
        tier=result.tier,
        depth=result.depth,
        lines=[
            StoredLine(
                rank=line.rank,
                eval=format_eval(line.evaluation()),
                moves_uci=line.moves_uci,
                moves_san=uci_line_to_san(result.fen, line.moves_uci),
            )
            for line in result.lines
        ],
    )
