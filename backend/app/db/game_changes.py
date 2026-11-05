"""Fixing a game after upload: change the player's color, or delete the game (PLAN_V3 M1).

Both exist because a game analyzed from the wrong side couldn't be fixed (v2-handoff). Every
function takes a game already checked to belong to the player (`OwnedGame`).
"""

from typing import cast

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.analysis.evals import Color
from app.analysis.game_info import user_result
from app.analysis.pgn import parse_pgn
from app.analysis.summary import build_summary
from app.analysis.summary_models import UserInfo
from app.config import Settings
from app.db.engine_results import load_results
from app.db.games import pending_verify_fens, record_analysis
from app.db.models import (
    ChatMessageRow,
    EngineResultRow,
    Game,
    GameSummaryRow,
    GameThemeFactRow,
    LlmUsageRow,
    MomentProgressRow,
    PendingToolCallRow,
)
from app.db.onboarding import filled_slots, onboarding_games, slot_for
from app.db.tendencies import refresh_tendencies
from app.db.variations import delete_variations


class SlotFullError(Exception):
    """An onboarding game's new color would put a fourth game in a slot."""


def change_color(session: Session, settings: Settings, game: Game, color: Color) -> None:
    """Switch the side the player played and redo everything that depends on it.

    The coach's messages, the synopsis and the critical-moment progress were about the other side,
    so they're cleared. An analyzed game is rebuilt from its stored engine results. Positions the
    new side needs verified and doesn't have yet send the game back to "scanned": the browser
    verifies just those the next time the game opens, and the summary is built then.
    """
    if game.user_color == color:
        return
    new_result = user_result(game.headers.get("Result"), color)
    if game.source == "onboarding":
        _check_slot(session, settings, game, color, new_result)
    game.user_color = color
    game.user_result = new_result
    _clear_coaching(session, game.id)
    if game.status == "analyzed":
        _reanalyze(session, settings, game)
    session.commit()


def delete_game(session: Session, settings: Settings, game: Game) -> None:
    """Delete the game and everything stored for it, then refresh the player's tendencies.
    Token usage is kept (it counts toward the daily budget) but no longer points at the game."""
    game_id, user_id = game.id, game.user_id
    session.execute(update(LlmUsageRow).where(LlmUsageRow.game_id == game_id).values(game_id=None))
    _clear_coaching(session, game_id)
    delete_variations(session, game_id)
    for table in (EngineResultRow, GameSummaryRow, GameThemeFactRow):
        session.execute(delete(table).where(table.game_id == game_id))
    session.delete(game)
    session.flush()
    if user_id is not None:
        refresh_tendencies(session, settings.tendencies, user_id)
    session.commit()


def _clear_coaching(session: Session, game_id: str) -> None:
    for table in (ChatMessageRow, PendingToolCallRow, MomentProgressRow):
        session.execute(delete(table).where(table.game_id == game_id))


def _reanalyze(session: Session, settings: Settings, game: Game) -> None:
    parsed = parse_pgn(
        game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
    )
    scan = load_results(session, game.id, ["scan"])
    if pending_verify_fens(session, parsed, game, scan, settings):
        session.execute(delete(GameSummaryRow).where(GameSummaryRow.game_id == game.id))
        session.execute(delete(GameThemeFactRow).where(GameThemeFactRow.game_id == game.id))
        game.status = "scanned"
        session.flush()
        if game.user_id is not None:
            refresh_tendencies(session, settings.tendencies, game.user_id)
        return
    info = UserInfo(color=cast(Color, game.user_color), elo=game.elo, playstyle=game.playstyle)
    results = load_results(session, game.id, ["scan", "verify"])
    record_analysis(session, settings, game, build_summary(parsed, results, info, settings))


def _check_slot(
    session: Session, settings: Settings, game: Game, color: Color, result: str | None
) -> None:
    others = [g for g in onboarding_games(session, cast(str, game.user_id)) if g.id != game.id]
    slot = slot_for(color, result)
    if filled_slots(others)[slot] >= settings.onboarding.games_per_slot:
        raise SlotFullError(slot)
