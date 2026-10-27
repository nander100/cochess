"""Turning a chat or Explain request into a coach Turn (SPEC_V2 §6): replay the board's path, check
and store the browser's engine result for that position, and load the position's lines."""

from typing import cast

import chess
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.analysis.engine import EngineResult, EngineResultError, Tier, check_for_position
from app.analysis.evals import Color, terminal_evaluation
from app.analysis.paths import PathError, resolve_path
from app.analysis.pgn import parse_pgn
from app.coach.chat import Turn
from app.coach.payload import profile_player
from app.coach.tools import line_summaries
from app.config import EngineTier, Settings
from app.db.engine_results import load_position_result, save_position_result
from app.db.models import Game, User

NEEDS_ANALYSIS = "The engine hasn't analyzed this position yet. Analyze it, then ask again."


def prepare_turn(
    session: Session,
    settings: Settings,
    game: Game,
    user: User,
    path_uci: list[str],
    engine_result: EngineResult | None,
    message: str | None,
) -> Turn:
    """Raises HTTPException (422 bad path or result, 409 no analysis) before any streaming."""
    parsed = parse_pgn(
        game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
    )
    try:
        path = resolve_path(parsed, path_uci, settings.limits.max_plies)
    except PathError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message) from error

    if engine_result is not None:
        tiers: dict[Tier, EngineTier] = {
            "verify": settings.engine.verify,
            "deep": settings.engine.deep,
        }
        try:
            checked = check_for_position(engine_result, fen=path.fen, tier_configs=tiers)
        except EngineResultError as error:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message
            ) from error
        save_position_result(session, game.id, checked)

    stored = load_position_result(session, game.id, path.fen)
    game_over = terminal_evaluation(chess.Board(path.fen)) is not None
    if stored is None and not game_over:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=NEEDS_ANALYSIS)
    lines = line_summaries(path.fen, stored) if stored is not None else []

    # The profile as it is now (PLAN_V2 §6 Q5); a v1 game's owner may not have filled it in yet.
    elo = user.elo if user.elo is not None else game.elo
    player = profile_player(elo, user.playstyle, cast(Color, game.user_color))
    return Turn(message=message, position=path, engine_lines=lines, player=player)
