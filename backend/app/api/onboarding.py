"""Onboarding (SPEC_V2 §10, §11): paste games, fill the 12 slots, analyze them, then the
baseline report. Everything is the current player's own."""

from collections.abc import Sequence
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.evals import Color
from app.analysis.game_info import opening_name, user_result
from app.analysis.onboarding import (
    SLOTS,
    Candidate,
    Category,
    SlotDecision,
    SplitGame,
    assign_slots,
    split_games,
    suggest_colors,
    time_control_category,
)
from app.analysis.pgn import ParsedGame, PgnError, parse_pgn
from app.api.budget import check_token_budget
from app.api.coach import ClientDep, session_factory, stream_coach, text_events
from app.api.deps import get_app_settings, get_session
from app.api.games import PROFILE_FIRST
from app.api.onboarding_schemas import (
    BaselineReport,
    GameChoice,
    OnboardingGame,
    OnboardingStatus,
    ParsedRow,
    ParseRequest,
    ParseResponse,
    SlotCount,
    SubmitRequest,
    SubmitResponse,
    SubmitResult,
)
from app.api.profile import is_complete
from app.api.schemas import GameStatus, PgnErrorDetail, PgnErrorResponse, TimeControl
from app.auth.deps import CurrentUser
from app.coach.baseline import BaselineResult, generate_baseline
from app.config import Settings
from app.db.games import game_fingerprint, new_game
from app.db.models import BaselineReportRow, Game, User
from app.db.onboarding import filled_slots, latest_report, onboarding_games, slot_of

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

NOT_READY = "Finish analyzing all 12 onboarding games first."


@router.post(
    "/parse", responses={status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": PgnErrorResponse}}
)
def parse(
    body: ParseRequest, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> ParseResponse:
    """The pasted games as a table, with the slot each would fill or why it can't (§10.3)."""
    primary = _primary(user)
    try:
        split = split_games(body.pgn_text, settings.limits, settings.onboarding)
    except PgnError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=_error(error).model_dump()
        ) from error
    games = [piece.game for piece in split]
    suggestions = suggest_colors(games)
    choices = [_choice(body.choices, i) for i in range(len(split))]
    colors = [c.user_color or s for c, s in zip(choices, suggestions, strict=True)]
    filled = onboarding_games(session, user.id)
    decisions = _decide(session, user, settings, games, colors, choices, filled, primary)
    rows = [
        _row(i, piece, suggestions[i], colors[i], decision, settings)
        for i, (piece, decision) in enumerate(zip(split, decisions, strict=True))
    ]
    return ParseResponse(
        primary_time_control=primary, games=rows, slots=_slot_counts(filled, settings)
    )


@router.post("/submit")
def submit(
    body: SubmitRequest, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> SubmitResponse:
    """Store the games that fill a slot as onboarding games, queued for analysis. The backend
    decides again from the PGNs: what the browser showed is only a preview."""
    primary = _primary(user)
    games = [_parse_one(item.pgn, settings) for item in body.games]
    colors: list[Color | None] = [item.user_color for item in body.games]
    choices = [
        GameChoice(user_color=item.user_color, time_control_category=item.time_control_category)
        for item in body.games
    ]
    filled = onboarding_games(session, user.id)
    decisions = _decide(session, user, settings, games, colors, choices, filled, primary)

    results = []
    stored = list(filled)
    for i, (game, decision, item) in enumerate(zip(games, decisions, body.games, strict=True)):
        game_id = None
        if game is not None and decision.slot is not None:
            category = _category(game, choices[i], settings)
            row = new_game(
                session, user, game, item.user_color, source="onboarding", category=category
            )
            session.flush()
            stored.append(row)
            game_id = row.id
        results.append(
            SubmitResult(index=i, slot=decision.slot, reason=decision.reason, game_id=game_id)
        )
    session.commit()
    return SubmitResponse(results=results, slots=_slot_counts(stored, settings))


@router.get("/status")
def onboarding_status(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> OnboardingStatus:
    """Slots, games, and analysis progress: the browser resumes analysis from this (§10.3)."""
    games = onboarding_games(session, user.id)
    analyzed = sum(game.status == "analyzed" for game in games)
    complete = _complete(games, settings)
    report = latest_report(session, user.id)
    return OnboardingStatus(
        primary_time_control=cast(TimeControl | None, user.time_control),
        slots=_slot_counts(games, settings),
        games=[_game(game) for game in games],
        complete=complete,
        analyzed=analyzed,
        report_ready=complete and analyzed == len(games),
        report=_report(report) if report else None,
    )


@router.get("/report")
def get_report(user: CurrentUser, session: SessionDep) -> BaselineReport:
    report = latest_report(session, user.id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No baseline report yet.")
    return _report(report)


@router.post("/report", dependencies=[Depends(check_token_budget)])
def write_report(
    user: CurrentUser,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client: ClientDep,
) -> StreamingResponse:
    """The baseline report (§10.4) as SSE. Written once for a set of 12 games, then shown again
    from storage."""
    games = onboarding_games(session, user.id)
    if not _complete(games, settings) or any(game.status != "analyzed" for game in games):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=NOT_READY)
    stored = latest_report(session, user.id)
    if stored is not None and stored.game_ids == [game.id for game in games]:
        result = BaselineResult(stored.text, list(stored.invalid_moves_removed), stored.game_ids)
        return stream_coach(_ready(result), _events, settings, "baseline")
    work = generate_baseline(client, settings, session_factory(request), user.id)
    return stream_coach(work, _events, settings, "baseline")


async def _ready(result: BaselineResult) -> BaselineResult:
    return result


def _events(result: BaselineResult) -> list[str]:
    return text_events(result.text, result.invalid_moves_removed)


def _primary(user: User) -> TimeControl:
    if not is_complete(user) or user.time_control is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=PROFILE_FIRST)
    return cast(TimeControl, user.time_control)


def _parse_one(pgn: str, settings: Settings) -> ParsedGame | None:
    try:
        return parse_pgn(
            pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
        )
    except PgnError:
        return None


def _choice(choices: Sequence[GameChoice | None], index: int) -> GameChoice:
    choice = choices[index] if index < len(choices) else None
    return choice or GameChoice()


def _category(game: ParsedGame, choice: GameChoice, settings: Settings) -> Category | None:
    """From the TimeControl header; the player's pick only when the header doesn't say."""
    from_header = time_control_category(game.headers.get("TimeControl"), settings.onboarding)
    return from_header or choice.time_control_category


def _decide(
    session: Session,
    user: User,
    settings: Settings,
    games: Sequence[ParsedGame | None],
    colors: Sequence[Color | None],
    choices: Sequence[GameChoice],
    filled: Sequence[Game],
    primary: TimeControl,
) -> list[SlotDecision]:
    """Slot decisions in order. A game the player already has, or one earlier in this batch,
    is a duplicate."""
    known = set(session.scalars(select(Game.fingerprint).where(Game.user_id == user.id)))
    candidates = []
    for game, color, choice in zip(games, colors, choices, strict=True):
        if game is None:
            candidates.append(Candidate(color=color, result=None, category=None, invalid=True))
            continue
        key = game_fingerprint(game)
        candidates.append(
            Candidate(
                color=color,
                result=user_result(game.headers.get("Result"), color) if color else None,
                category=_category(game, choice, settings),
                duplicate=key in known,
            )
        )
        known.add(key)
    return assign_slots(filled_slots(filled), candidates, primary, settings.onboarding)


def _row(
    index: int,
    piece: SplitGame,
    suggested: Color | None,
    color: Color | None,
    decision: SlotDecision,
    settings: Settings,
) -> ParsedRow:
    headers = piece.game.headers if piece.game else {}
    return ParsedRow(
        index=index,
        pgn=piece.game.pgn if piece.game else None,
        white=headers.get("White"),
        black=headers.get("Black"),
        result=headers.get("Result"),
        date=headers.get("UTCDate") or headers.get("Date"),
        time_control=headers.get("TimeControl"),
        category=time_control_category(headers.get("TimeControl"), settings.onboarding),
        error=_error(piece.error) if piece.error else None,
        suggested_color=suggested,
        user_color=color,
        user_result=user_result(headers.get("Result"), color) if color and piece.game else None,
        slot=decision.slot,
        reason=decision.reason,
    )


def _error(error: PgnError) -> PgnErrorDetail:
    return PgnErrorDetail(code=error.code, message=error.message, move_number=error.move_number)


def _slot_counts(games: Sequence[Game], settings: Settings) -> list[SlotCount]:
    filled = filled_slots(games)
    per_slot = settings.onboarding.games_per_slot
    return [SlotCount(slot=slot, filled=filled[slot], of=per_slot) for slot in SLOTS]


def _complete(games: Sequence[Game], settings: Settings) -> bool:
    filled = filled_slots(games)
    return all(filled[slot] >= settings.onboarding.games_per_slot for slot in SLOTS)


def _game(game: Game) -> OnboardingGame:
    color = cast(Color, game.user_color)
    return OnboardingGame(
        id=game.id,
        slot=slot_of(game),
        status=cast(GameStatus, game.status),
        opponent=game.headers.get("Black" if color == "white" else "White", "?"),
        played_at=game.played_at or game.created_at,
        opening=opening_name(game.headers),
    )


def _report(row: BaselineReportRow) -> BaselineReport:
    return BaselineReport(
        text=row.text,
        invalid_moves_removed=list(row.invalid_moves_removed),
        game_ids=list(row.game_ids),
        created_at=row.created_at,
    )
