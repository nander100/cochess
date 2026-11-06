"""POST /api/onboarding/import: the assessment's games straight from Chess.com or Lichess.

The player's recent games in their main time control are fetched, their color is found from
their username, and the newest games that fill the empty slots (3 wins and 3 losses with each
color, owner request 2026-11-06) are picked by the same rules as a paste. Only those games come
back, so the paste table never gets more than the 12 it needs."""

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.analysis.evals import Color
from app.analysis.onboarding import SLOTS, Slot, detect_color
from app.analysis.pgn import ParsedGame, PgnError, parse_pgn
from app.api.deps import get_app_settings, get_session
from app.api.imports import fetch_recent
from app.api.onboarding import decide_slots, primary_time_control
from app.api.onboarding_schemas import GameChoice
from app.api.schemas import Platform
from app.auth.deps import CurrentUser
from app.config import Settings
from app.db.onboarding import filled_slots, onboarding_games
from app.db.user_settings import usernames_for

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


class AssessmentImportRequest(BaseModel):
    platform: Platform


class PickedGame(BaseModel):
    pgn: str  # the cleaned PGN, ready for the paste table
    external_id: str


class MissingSlot(BaseModel):
    slot: Slot
    count: int


class AssessmentImport(BaseModel):
    platform: Platform
    username: str
    fetched: int  # how many recent games were looked at
    games: list[PickedGame]  # newest first, at most what the empty slots need
    missing: list[MissingSlot]  # slots these games still don't fill


@router.post("/import")
def import_for_assessment(
    body: AssessmentImportRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> AssessmentImport:
    primary = primary_time_control(user)
    username, fetched = fetch_recent(
        request,
        session,
        user.id,
        settings,
        body.platform,
        settings.imports.assessment_games,
        category=primary,
    )
    games = [_parse(game.pgn, settings) for game in fetched]
    usernames = usernames_for(session, user.id)
    colors: list[Color | None] = [detect_color(game, usernames) for game in games]
    choices = [GameChoice(user_color=color) for color in colors]
    filled = onboarding_games(session, user.id)
    decisions = decide_slots(session, user, settings, games, colors, choices, filled, primary)
    picked: list[PickedGame] = []
    taken: Counter[Slot] = Counter()
    for game, imported, decision in zip(games, fetched, decisions, strict=True):
        if game is not None and decision.slot is not None:
            picked.append(PickedGame(pgn=game.pgn, external_id=imported.external_id))
            taken[decision.slot] += 1
    have = filled_slots(filled)
    per_slot = settings.onboarding.games_per_slot
    missing = [
        MissingSlot(slot=slot, count=per_slot - have[slot] - taken[slot])
        for slot in SLOTS
        if per_slot - have[slot] - taken[slot] > 0
    ]
    return AssessmentImport(
        platform=body.platform,
        username=username,
        fetched=len(fetched),
        games=picked,
        missing=missing,
    )


def _parse(pgn: str, settings: Settings) -> ParsedGame | None:
    try:
        return parse_pgn(
            pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
        )
    except PgnError:
        return None  # unreadable or a non-standard start: never picked
