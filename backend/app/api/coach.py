"""Coach routes (SPEC §9). Responses are SSE: `status`, then `text` chunks, then `done`, or
`error`. Text is sent only after move validation (PLAN Q22)."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from app.api import sse
from app.api.deps import get_app_settings, get_session
from app.coach.client import CoachClient, CoachUnavailableError
from app.coach.service import generate_synopsis
from app.config import Settings
from app.db.engine_results import load_summary
from app.db.models import Game

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/games", tags=["coach"])


def get_coach_client(request: Request) -> CoachClient:
    client = cast(CoachClient | None, request.app.state.coach_client)
    if client is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The coach isn't set up on this server yet (missing ANTHROPIC_API_KEY).",
        )
    return client


@router.post("/{game_id}/synopsis")
def synopsis(
    game_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    client: Annotated[CoachClient, Depends(get_coach_client)],
) -> StreamingResponse:
    if session.get(Game, game_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Game not found.")
    if load_summary(session, game_id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Finish the engine analysis first.")
    sessions = cast(sessionmaker[Session], request.app.state.session_factory)
    return StreamingResponse(
        _synopsis_events(client, settings, sessions, game_id),
        media_type="text/event-stream",
        headers=sse.SSE_HEADERS,
    )


async def _synopsis_events(
    client: CoachClient, settings: Settings, sessions: sessionmaker[Session], game_id: str
) -> AsyncIterator[str]:
    yield sse.event("status", {"message": "Coach is writing…"})
    task = asyncio.create_task(generate_synopsis(client, settings, sessions, game_id))
    while not task.done():
        await asyncio.wait({task}, timeout=settings.coach.keepalive_s)
        if not task.done():
            yield sse.KEEPALIVE
    try:
        result = task.result()
    except CoachUnavailableError as error:
        yield sse.event("error", {"message": error.message})
        return
    except Exception:
        logger.exception("synopsis failed: game=%s", game_id)
        yield sse.event("error", {"message": "Something went wrong writing your synopsis."})
        return
    for piece in sse.chunks(result.text):
        yield sse.event("text", {"text": piece})
    yield sse.event("done", {"invalid_moves_removed": result.invalid_moves_removed})
