"""Critical-moment routes (SPEC_V2 §8.2). Each step is checked and saved before the coach is
called; the answer streams as SSE like the other coach routes. An attempt's first event is
`moment` with the grade and the new state, so the board can react before the text arrives."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analysis.engine import EngineResult
from app.api import sse
from app.api.budget import check_token_budget
from app.api.coach import (
    ClientDep,
    SessionDep,
    SettingsDep,
    require_summary,
    session_factory,
    stream_coach,
    text_events,
)
from app.api.scoping import OwnedGame
from app.api.turns import current_player
from app.auth.deps import CurrentUser
from app.coach.client import CoachClient
from app.coach.moments import (
    MomentAnswer,
    MomentCall,
    MomentError,
    answer,
    prepare_attempt,
    prepare_question,
    prepare_reveal,
    prepare_start,
    prepare_wrap_up,
)
from app.config import Settings
from app.db.moments import load_progress

router = APIRouter(
    prefix="/api/games", tags=["moments"], dependencies=[Depends(check_token_budget)]
)


class AttemptRequest(BaseModel):
    """The player's move and, optionally, why. The browser sends its deep searches of the
    position before (once per moment) and after the move; the backend checks both."""

    move_uci: str = Field(min_length=4, max_length=5)
    reasoning: str | None = Field(default=None, max_length=2000)
    engine_before: EngineResult | None = None
    engine_after: EngineResult | None = None


class RevealRequest(BaseModel):
    engine_before: EngineResult | None = None


class QuestionRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@router.post("/{game_id}/moments/{index}/start")
def start(
    game: OwnedGame,
    user: CurrentUser,
    index: int,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client: ClientDep,
) -> StreamingResponse:
    player = current_player(session, settings, user, game)
    return _respond(
        lambda: prepare_start(session, settings, game, player, index),
        request,
        session,
        settings,
        client,
        game.id,
    )


@router.post("/{game_id}/moments/{index}/attempt")
def attempt(
    game: OwnedGame,
    user: CurrentUser,
    index: int,
    body: AttemptRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client: ClientDep,
) -> StreamingResponse:
    player = current_player(session, settings, user, game)
    return _respond(
        lambda: prepare_attempt(
            session,
            settings,
            game,
            player,
            index,
            body.move_uci,
            body.reasoning,
            body.engine_before,
            body.engine_after,
        ),
        request,
        session,
        settings,
        client,
        game.id,
    )


@router.post("/{game_id}/moments/{index}/reveal")
def reveal(
    game: OwnedGame,
    user: CurrentUser,
    index: int,
    body: RevealRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client: ClientDep,
) -> StreamingResponse:
    player = current_player(session, settings, user, game)
    return _respond(
        lambda: prepare_reveal(session, settings, game, player, index, body.engine_before),
        request,
        session,
        settings,
        client,
        game.id,
    )


@router.post("/{game_id}/moments/{index}/ask")
def ask(
    game: OwnedGame,
    user: CurrentUser,
    index: int,
    body: QuestionRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client: ClientDep,
) -> StreamingResponse:
    message = body.message.strip()
    if not message:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Ask a question first.")
    _check_question_limit(session, settings, game.id)
    player = current_player(session, settings, user, game)
    return _respond(
        lambda: prepare_question(session, settings, game, player, index, message),
        request,
        session,
        settings,
        client,
        game.id,
    )


@router.post("/{game_id}/moments/wrap_up")
def wrap_up(
    game: OwnedGame,
    user: CurrentUser,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client: ClientDep,
) -> StreamingResponse:
    player = current_player(session, settings, user, game)
    return _respond(
        lambda: prepare_wrap_up(session, settings, game, player),
        request,
        session,
        settings,
        client,
        game.id,
    )


def _respond(
    prepare: Callable[[], MomentCall | MomentAnswer],
    request: Request,
    session: Session,
    settings: Settings,
    client: CoachClient,
    game_id: str,
) -> StreamingResponse:
    require_summary(session, game_id)
    try:
        prepared = prepare()
    except MomentError as error:
        raise HTTPException(error.status, detail=error.message) from error
    if isinstance(prepared, MomentAnswer):  # a stored intro or wrap-up: no new coach call
        return stream_coach(_ready(prepared), _events, settings, game_id)
    work = answer(client, settings, session_factory(request), prepared)
    return stream_coach(work, _events, settings, game_id)


async def _ready(result: MomentAnswer) -> MomentAnswer:
    return result


def _events(result: MomentAnswer) -> list[str]:
    meta = [sse.event("moment", result.meta)] if result.meta else []
    return [*meta, *text_events(result.text, result.invalid_moves_removed)]


def _check_question_limit(session: Session, settings: Settings, game_id: str) -> None:
    """Questions during moments get the same per-game allowance as chat (PLAN Q27)."""
    limit = settings.coach.chat_max_messages
    asked = sum(
        1
        for row in load_progress(session, game_id).values()
        for message in row.messages
        if message.get("kind") == "question"
    )
    if asked >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You've reached the limit of {limit} questions for this game's moments.",
        )
