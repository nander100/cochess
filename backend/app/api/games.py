"""Game routes (SPEC_V2 §11). Every game belongs to the player who uploaded it."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.evals import Color
from app.analysis.game_info import opening_name
from app.analysis.onboarding import time_control_category
from app.analysis.pgn import PgnError, parse_pgn
from app.api.deps import get_app_settings, get_session
from app.api.game_detail import build_detail
from app.api.profile import is_complete
from app.api.schemas import (
    ChangeColorRequest,
    CreateGameRequest,
    CreateGameResponse,
    GameDetail,
    GameListItem,
    GameStatus,
    PgnErrorDetail,
    PgnErrorResponse,
    UserResult,
)
from app.api.scoping import OwnedGame
from app.auth.deps import CurrentUser
from app.config import Settings
from app.db.game_changes import SlotFullError, change_color, delete_game
from app.db.games import find_duplicate, game_fingerprint, list_games, new_game
from app.db.models import Game

router = APIRouter(prefix="/api/games", tags=["games"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

PROFILE_FIRST = "Fill in your profile (rating and time control) before analyzing a game."
DUPLICATE = "You've already uploaded this game. Open it from My games."
SLOT_FULL = "That would make four games in one assessment slot. Remove a game from that slot first."


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": PgnErrorResponse}},
)
def create_game(
    body: CreateGameRequest,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> CreateGameResponse:
    if not is_complete(user) or user.elo is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=PROFILE_FIRST)
    _check_daily_cap(session, user.id, settings)
    try:
        parsed = parse_pgn(
            body.pgn,
            max_chars=settings.limits.max_pgn_chars,
            max_plies=settings.limits.max_plies,
        )
    except PgnError as error:
        detail = PgnErrorDetail(
            code=error.code, message=error.message, move_number=error.move_number
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail.model_dump()
        ) from error

    if find_duplicate(session, user.id, game_fingerprint(parsed)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=DUPLICATE)
    game = new_game(session, user, parsed, body.user_color, source="single")
    session.commit()

    return CreateGameResponse(
        game_id=game.id,
        positions=list(parsed.positions),
        final_fen=parsed.final_fen,
        final_is_terminal=parsed.final_is_terminal,
    )


@router.get("")
def my_games(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> list[GameListItem]:
    """My games (SPEC_V2 §11), most recently played first."""
    items = []
    for listed in list_games(session, user.id):
        game, headers = listed.game, listed.game.headers
        color = cast(Color, game.user_color)
        opponent = headers.get("Black" if color == "white" else "White", "?")
        items.append(
            GameListItem(
                id=game.id,
                played_at=game.played_at or game.created_at,
                opponent=opponent,
                user_color=color,
                user_result=cast(UserResult | None, game.user_result),
                time_control=headers.get("TimeControl"),
                opening=opening_name(headers),
                accuracy=listed.accuracy,
                status=cast(GameStatus, game.status),
                time_control_category=game.time_control_category
                or time_control_category(headers.get("TimeControl"), settings.onboarding),
                moments_total=listed.moments_total,
                moments_done=listed.moments_done,
            )
        )
    return items


@router.get("/{game_id}")
def game_detail(game: OwnedGame, session: SessionDep, settings: SettingsDep) -> GameDetail:
    """Everything the analysis board needs, from the database (SPEC_V2 §5.1)."""
    return build_detail(session, game, settings)


@router.patch("/{game_id}")
def change_game_color(
    game: OwnedGame, body: ChangeColorRequest, session: SessionDep, settings: SettingsDep
) -> GameDetail:
    """Switch the side the player played (PLAN_V3 M1). The coach's messages and moment progress
    are cleared; the analysis is rebuilt from stored results, or the game goes back to "scanned"
    if the new side needs positions verified (the returned `verify_fens`)."""
    try:
        change_color(session, settings, game, body.user_color)
    except SlotFullError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=SLOT_FULL) from error
    return build_detail(session, game, settings)


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_game(game: OwnedGame, session: SessionDep, settings: SettingsDep) -> None:
    """Delete the game and everything stored for it (PLAN_V3 M1). Also removes an onboarding
    game, freeing its slot."""
    delete_game(session, settings, game)


def _check_daily_cap(session: Session, user_id: str, settings: Settings) -> None:
    """New single-game uploads per player per rolling 24 hours (PLAN_V2 §6 Q8)."""
    cap = settings.limits.max_games_per_day
    since = datetime.now(UTC) - timedelta(days=1)
    recent = (
        session.scalar(
            select(func.count()).where(
                Game.user_id == user_id, Game.source == "single", Game.created_at >= since
            )
        )
        or 0
    )
    if recent >= cap:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"CoChess analyzes at most {cap} new games a day per player while in "
            "testing. Please try again tomorrow.",
        )
