"""Game routes (SPEC §9)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.analysis.pgn import PgnError, parse_pgn
from app.api.deps import get_app_settings, get_session
from app.api.schemas import CreateGameRequest, CreateGameResponse, PgnErrorDetail, PgnErrorResponse
from app.config import Settings
from app.db.models import Game

router = APIRouter(prefix="/api/games", tags=["games"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": PgnErrorResponse}},
)
def create_game(
    body: CreateGameRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> CreateGameResponse:
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

    game = Game(
        pgn=parsed.pgn,
        user_color=body.user_color,
        elo=body.elo,
        playstyle=body.playstyle,
        headers=parsed.headers,
    )
    session.add(game)
    session.commit()

    return CreateGameResponse(
        game_id=game.id,
        positions=list(parsed.positions),
        final_fen=parsed.final_fen,
        final_is_terminal=parsed.final_is_terminal,
    )
