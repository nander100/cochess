"""Coach routes (SPEC §9). Responses are SSE: `status`, keepalives while the coach works, then
`text` chunks and `done`, or `engine_request` (chat), or `error`. Text is sent only after move
validation (PLAN Q22)."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.engine import EngineResult, EngineResultError
from app.api import sse
from app.api.budget import check_token_budget
from app.api.deps import get_app_settings, get_session
from app.api.scoping import OwnedGame
from app.api.turns import prepare_turn
from app.auth.deps import CurrentUser
from app.coach.chat import (
    ChatLimitError,
    ChatOutcome,
    EngineRequest,
    FinalAnswer,
    PendingNotFoundError,
    check_engine_results,
    explain,
    send_message,
    submit_engine_results,
)
from app.coach.client import CoachClient, CoachUnavailableError
from app.coach.service import SynopsisResult, generate_synopsis
from app.config import Settings
from app.db.chat import count_player_messages
from app.db.engine_results import load_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/games", tags=["coach"], dependencies=[Depends(check_token_budget)])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_coach_client(request: Request) -> CoachClient:
    client = cast(CoachClient | None, request.app.state.coach_client)
    if client is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The coach isn't set up on this server yet (missing ANTHROPIC_API_KEY).",
        )
    return client


ClientDep = Annotated[CoachClient, Depends(get_coach_client)]


# A path can't be longer than the longest game plus a short variation; the replay checks the limit.
MAX_PATH = 1000


class ChatRequest(BaseModel):
    """SPEC_V2 §6.2: the message, the board position it's about, and the browser's engine result
    for that position when the backend doesn't have one yet."""

    message: str = Field(min_length=1)
    path_uci: list[str] = Field(default_factory=list, max_length=MAX_PATH)
    engine_result: EngineResult | None = None


class ExplainRequest(BaseModel):
    path_uci: list[str] = Field(default_factory=list, max_length=MAX_PATH)
    engine_result: EngineResult | None = None


class EngineResultSubmission(BaseModel):
    request_id: str
    results: list[EngineResult]


@router.post("/{game_id}/synopsis")
def synopsis(
    game: OwnedGame, request: Request, session: SessionDep, settings: SettingsDep, client: ClientDep
) -> StreamingResponse:
    game_id = game.id
    require_summary(session, game_id)
    work = generate_synopsis(client, settings, session_factory(request), game_id)
    return stream_coach(work, _synopsis_events, settings, game_id)


@router.post("/{game_id}/chat")
def chat(
    game: OwnedGame,
    user: CurrentUser,
    body: ChatRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client: ClientDep,
) -> StreamingResponse:
    game_id = game.id
    require_summary(session, game_id)
    message = body.message.strip()
    limits = settings.coach
    if not message or len(message) > limits.chat_max_message_chars:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Messages can be 1 to {limits.chat_max_message_chars} characters long.",
        )
    _check_message_limit(session, settings, game_id)
    turn = prepare_turn(session, settings, game, user, body.path_uci, body.engine_result, message)
    work = send_message(client, settings, session_factory(request), game_id, turn)
    return stream_coach(work, _chat_events, settings, game_id)


@router.post("/{game_id}/explain")
def explain_position(
    game: OwnedGame,
    user: CurrentUser,
    body: ExplainRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client: ClientDep,
) -> StreamingResponse:
    """SPEC_V2 §6.3: explain the position on the board; the answer joins the chat."""
    game_id = game.id
    require_summary(session, game_id)
    _check_message_limit(session, settings, game_id)
    turn = prepare_turn(session, settings, game, user, body.path_uci, body.engine_result, None)
    work = explain(client, settings, session_factory(request), game_id, turn)
    return stream_coach(work, _answer_events, settings, game_id)


@router.post("/{game_id}/chat/engine_result")
def chat_engine_result(
    game: OwnedGame,
    body: EngineResultSubmission,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client: ClientDep,
) -> StreamingResponse:
    game_id = game.id
    require_summary(session, game_id)
    sessions = session_factory(request)
    try:
        results = check_engine_results(sessions, settings, game_id, body.request_id, body.results)
    except PendingNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="That analysis is no longer pending."
        ) from error
    except EngineResultError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message) from error
    work = submit_engine_results(client, settings, sessions, game_id, body.request_id, results)
    return stream_coach(work, _chat_events, settings, game_id)


def _check_message_limit(session: Session, settings: Settings, game_id: str) -> None:
    """Questions and Explain requests per game share one limit (PLAN Q27)."""
    limit = settings.coach.chat_max_messages
    if count_player_messages(session, game_id) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You've reached the limit of {limit} questions for this game.",
        )


def require_summary(session: Session, game_id: str) -> None:
    if load_summary(session, game_id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Finish the engine analysis first.")


def session_factory(request: Request) -> sessionmaker[Session]:
    return cast(sessionmaker[Session], request.app.state.session_factory)


def stream_coach[T](
    work: Coroutine[Any, Any, T],
    render: Callable[[T], list[str]],
    settings: Settings,
    game_id: str,
) -> StreamingResponse:
    return StreamingResponse(
        _events(work, render, settings, game_id),
        media_type="text/event-stream",
        headers=sse.SSE_HEADERS,
    )


async def _events[T](
    work: Coroutine[Any, Any, T],
    render: Callable[[T], list[str]],
    settings: Settings,
    game_id: str,
) -> AsyncIterator[str]:
    yield sse.event("status", {"message": "Coach is writing…"})
    task = asyncio.create_task(work)
    while not task.done():
        await asyncio.wait({task}, timeout=settings.coach.keepalive_s)
        if not task.done():
            yield sse.KEEPALIVE
    try:
        result = task.result()
    except (CoachUnavailableError, ChatLimitError) as error:
        yield sse.event("error", {"message": error.message})
        return
    except Exception:
        logger.exception("coach request failed: game=%s", game_id)
        yield sse.event("error", {"message": "Something went wrong. Please try again."})
        return
    for event in render(result):
        yield event


def text_events(text: str, removed: list[str]) -> list[str]:
    pieces = [sse.event("text", {"text": piece}) for piece in sse.chunks(text)]
    return [*pieces, sse.event("done", {"invalid_moves_removed": removed})]


def _synopsis_events(result: SynopsisResult) -> list[str]:
    return text_events(result.text, result.invalid_moves_removed)


def _answer_events(answer: FinalAnswer) -> list[str]:
    return text_events(answer.text, answer.invalid_moves_removed)


def _chat_events(outcome: ChatOutcome) -> list[str]:
    if isinstance(outcome, EngineRequest):
        positions = [p.model_dump() for p in outcome.positions]
        data = {"request_id": outcome.request_id, "tier": "deep", "positions": positions}
        return [sse.event("engine_request", data)]
    return text_events(outcome.text, outcome.invalid_moves_removed)
