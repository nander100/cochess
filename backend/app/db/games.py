"""Game access, always scoped to one user (SPEC_V2 §4.2): another user's game is "not found"."""

from datetime import UTC, datetime
from typing import Any, NamedTuple, cast

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.analysis.engine import EngineResult, best_by_fen, position_evaluations
from app.analysis.evals import Color
from app.analysis.game_info import fingerprint, played_at, user_result
from app.analysis.pgn import ParsedGame, parse_pgn
from app.analysis.selection import select_verify_plies, still_to_verify, verify_fens
from app.analysis.summary import build_summary
from app.analysis.summary_models import GameSummary, UserInfo
from app.config import Settings
from app.db.engine_results import load_results, save_summary
from app.db.models import (
    EngineResultRow,
    Game,
    GameSummaryRow,
    LlmUsageRow,
    MomentProgressRow,
    User,
)
from app.db.tendencies import refresh_tendencies, save_theme_facts


class GameNotFoundError(Exception):
    pass


def get_game(session: Session, user_id: str, game_id: str) -> Game:
    game = session.get(Game, game_id)
    if game is None or game.user_id != user_id:
        raise GameNotFoundError(game_id)
    return game


def new_game(
    session: Session,
    user: User,
    parsed: ParsedGame,
    color: Color,
    *,
    source: str,
    category: str | None = None,
    external: tuple[str, str] | None = None,
) -> Game:
    """Store an uploaded game for `user` (the caller commits). Elo and playstyle are the
    profile's at upload: the Elo at analysis, kept even if the profile changes later."""
    now = datetime.now(UTC)
    game = Game(
        user_id=user.id,
        pgn=parsed.pgn,
        user_color=color,
        elo=user.elo,
        playstyle=user.playstyle,
        headers=parsed.headers,
        played_at=played_at(parsed.headers) or now,
        user_result=user_result(parsed.headers.get("Result"), color),
        time_control_category=category,
        source=source,
        fingerprint=game_fingerprint(parsed),
        external_source=external[0] if external else None,
        external_id=external[1] if external else None,
        created_at=now,
    )
    session.add(game)
    return game


def game_fingerprint(parsed: ParsedGame) -> str:
    return fingerprint(parsed.headers, [p.uci for p in parsed.positions])


def find_duplicate(session: Session, user_id: str, key: str) -> Game | None:
    """The player's game with this fingerprint, if they've uploaded it before."""
    return session.scalars(
        select(Game).where(Game.user_id == user_id, Game.fingerprint == key).limit(1)
    ).first()


def find_external(session: Session, user_id: str, platform: str, external_id: str) -> Game | None:
    """The player's game imported from this platform game, if they've added it before."""
    return session.scalars(
        select(Game)
        .where(
            Game.user_id == user_id,
            Game.external_source == platform,
            Game.external_id == external_id,
        )
        .limit(1)
    ).first()


def fill_fingerprints(session: Session, settings: Settings) -> list[list[Game]]:
    """(Re)compute every game's fingerprint, so games uploaded before fingerprints existed, or
    before their definition changed, get the current one. Returns the duplicate groups (same
    player, same fingerprint), oldest upload first, for the owner to review."""
    for game in session.scalars(select(Game)):
        parsed = parse_pgn(
            game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
        )
        game.fingerprint = game_fingerprint(parsed)
    session.commit()
    groups: dict[tuple[str | None, str | None], list[Game]] = {}
    for game in session.scalars(select(Game).order_by(Game.created_at)):
        groups.setdefault((game.user_id, game.fingerprint), []).append(game)
    return [games for games in groups.values() if len(games) > 1]


def assign_unowned_games(session: Session, user: User) -> int:
    """Give every game without an owner (v1 games) to `user`, with the facts v1 didn't store.
    Returns how many games were assigned."""
    games = list(session.scalars(select(Game).where(Game.user_id.is_(None))))
    for game in games:
        game.user_id = user.id
        game.played_at = played_at(game.headers) or game.created_at
        game.user_result = user_result(game.headers.get("Result"), cast(Color, game.user_color))
    ids = [game.id for game in games]
    for table in (EngineResultRow, LlmUsageRow):
        session.execute(
            update(table)
            .where(table.game_id.in_(ids), table.user_id.is_(None))
            .values(user_id=user.id)
        )
    session.commit()
    return len(games)


class ListedGame(NamedTuple):
    game: Game
    accuracy: float | None  # the player's, once analyzed
    moments_total: int
    moments_done: int  # solved or revealed


def list_games(session: Session, user_id: str) -> list[ListedGame]:
    """The player's games, most recently played first, with the player's accuracy and how many
    critical moments are finished, once analyzed."""
    rows = session.execute(
        select(Game, GameSummaryRow.summary)
        .outerjoin(GameSummaryRow, GameSummaryRow.game_id == Game.id)
        .where(Game.user_id == user_id)
        .order_by(Game.played_at.desc(), Game.created_at.desc())
    ).all()
    finished = session.execute(
        select(MomentProgressRow.game_id, func.count())
        .where(
            MomentProgressRow.user_id == user_id,
            MomentProgressRow.state.in_(["solved", "revealed"]),
        )
        .group_by(MomentProgressRow.game_id)
    ).all()
    done = {game_id: count for game_id, count in finished}
    return [
        ListedGame(game, _user_accuracy(summary), _moment_count(summary), done.get(game.id, 0))
        for game, summary in rows
    ]


def _moment_count(summary: dict[str, Any] | None) -> int:
    moments = (summary or {}).get("moments") or []
    return len(moments) if isinstance(moments, list) else 0


def _user_accuracy(summary: dict[str, Any] | None) -> float | None:
    accuracy = (summary or {}).get("accuracy") or {}
    value = accuracy.get("user")
    return float(value) if isinstance(value, int | float) else None


def pending_verify_fens(
    session: Session,
    parsed: ParsedGame,
    game: Game,
    scan_results: list[EngineResult],
    settings: Settings,
) -> list[str]:
    """The positions the verify step still needs: chosen from the scan for the player's color,
    minus any already verified (after a color change, PLAN_V3 decision log)."""
    evals = position_evaluations(parsed, best_by_fen(scan_results))
    user_color = cast(Color, game.user_color)  # validated on upload
    chosen = verify_fens(parsed, select_verify_plies(evals, user_color, settings.thresholds))
    return still_to_verify(chosen, load_results(session, game.id, ["verify", "deep"]))


def record_analysis(session: Session, settings: Settings, game: Game, summary: GameSummary) -> None:
    """Store an analyzed game's summary and theme facts, then refresh the player's tendencies
    (SPEC_V2 §9.2: recomputed after every analyzed game). The caller commits."""
    save_summary(session, game.id, summary)
    save_theme_facts(session, game, summary)
    game.status = "analyzed"
    if game.user_id is not None:
        refresh_tendencies(session, settings.tendencies, game.user_id)


def rebuild_summaries(session: Session, settings: Settings, user: User | None = None) -> int:
    """Rebuild every analyzed game's summary (or one player's) from its stored engine results,
    so summaries made by older code gain what's been added since (e.g. moments, theme facts).
    No engine runs. Each player's tendencies are refreshed once at the end. Returns how many
    were rebuilt."""
    query = select(Game).where(Game.status == "analyzed")
    if user is not None:
        query = query.where(Game.user_id == user.id)
    games = list(session.scalars(query))
    for game in games:
        parsed = parse_pgn(
            game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
        )
        info = UserInfo(color=cast(Color, game.user_color), elo=game.elo, playstyle=game.playstyle)
        results = load_results(session, game.id, ["scan", "verify"])
        summary = build_summary(parsed, results, info, settings)
        save_summary(session, game.id, summary)
        save_theme_facts(session, game, summary)
    for user_id in sorted({game.user_id for game in games if game.user_id is not None}):
        refresh_tendencies(session, settings.tendencies, user_id)
    session.commit()
    return len(games)
