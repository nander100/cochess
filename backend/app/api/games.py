"""Game routes (SPEC_V2 §11). Every game belongs to the player who uploaded it."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.evals import Color
from app.analysis.game_info import fingerprint, opening_name, played_at, user_result
from app.analysis.pgn import PgnError, parse_pgn
from app.api.deps import get_app_settings, get_session
from app.api.game_detail import build_detail
from app.api.profile import is_complete
from app.api.schemas import (
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
from app.db.games import find_duplicate, list_games
from app.db.models import Game

router = APIRouter(prefix="/api/games", tags=["games"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

PROFILE_FIRST = "Fill in your profile (rating and time control) before analyzing a game."
DUPLICATE = "You've already uploaded this game. Open it from My games."


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

    key = fingerprint(parsed.headers, [p.uci for p in parsed.positions])
    if find_duplicate(session, user.id, key) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=DUPLICATE)

    now = datetime.now(UTC)
    game = Game(
        user_id=user.id,
        pgn=parsed.pgn,
        user_color=body.user_color,
        elo=user.elo,  # the Elo at analysis time; the profile can change later
        playstyle=user.playstyle,
        headers=parsed.headers,
        played_at=played_at(parsed.headers) or now,
        user_result=user_result(parsed.headers.get("Result"), body.user_color),
        source="single",
        fingerprint=key,
        created_at=now,
    )
    session.add(game)
    session.commit()

    return CreateGameResponse(
        game_id=game.id,
        positions=list(parsed.positions),
        final_fen=parsed.final_fen,
        final_is_terminal=parsed.final_is_terminal,
    )


@router.get("")
def my_games(user: CurrentUser, session: SessionDep) -> list[GameListItem]:
    """My games (SPEC_V2 §11), most recently played first."""
    items = []
    for game, accuracy in list_games(session, user.id):
        headers = game.headers
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
                accuracy=accuracy,
                status=cast(GameStatus, game.status),
            )
        )
    return items


@router.get("/{game_id}")
def game_detail(game: OwnedGame, session: SessionDep, settings: SettingsDep) -> GameDetail:
    """Everything the analysis board needs, from the database (SPEC_V2 §5.1)."""
    return build_detail(session, game, settings)


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
