"""Line walkthroughs (SPEC_V3 §7, §11.1): `POST /api/games/{id}/walkthrough` with the starting
path, the line (UCI) and the browser's scan of every position along it. Everything is checked
before the coach is called; the answer streams as SSE like the other coach routes, ending with a
`walkthrough` event. A line walked before is served from the cache without a coach call."""

from collections.abc import Sequence

import chess
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analysis.engine import EngineResult, EngineResultError, Tier, check_for_position
from app.analysis.evals import terminal_evaluation
from app.analysis.moments import good_first_moves
from app.analysis.paths import PathError, ResolvedPath, position_key, resolve_path
from app.analysis.pgn import parse_pgn
from app.api import sse
from app.api.budget import check_token_budget
from app.api.coach import (
    MAX_PATH,
    ClientDep,
    SessionDep,
    SettingsDep,
    require_summary,
    session_factory,
    stream_coach,
)
from app.api.scoping import OwnedGame
from app.api.turns import current_player
from app.auth.deps import CurrentUser
from app.coach.walkthrough import Walkthrough, build_call, generate
from app.config import EngineTier, Settings
from app.db.engine_results import load_position_result, load_summary
from app.db.models import Game
from app.db.moments import load_progress
from app.db.walkthroughs import load_walkthrough, save_walkthrough, walkthroughs_written

router = APIRouter(
    prefix="/api/games", tags=["walkthrough"], dependencies=[Depends(check_token_budget)]
)

UNSOLVED = "Solve or reveal this critical moment first: its best line is yours to find."
NEEDS_SCAN = "Analyze every position of the line with the engine first."
MAX_LINE = 10  # the schema's ceiling; settings.coach.walkthrough_max_plies can be lower


class WalkthroughRequest(BaseModel):
    start_path_uci: list[str] = Field(default_factory=list, max_length=MAX_PATH)
    line_uci: list[str] = Field(min_length=1, max_length=MAX_LINE)
    # A search of the start and of the position after each move: at most one more than the line.
    step_results: list[EngineResult] = Field(default_factory=list, max_length=MAX_LINE + 1)


@router.post("/{game_id}/walkthrough")
def walkthrough(
    game: OwnedGame,
    user: CurrentUser,
    body: WalkthroughRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    client: ClientDep,
) -> StreamingResponse:
    require_summary(session, game.id)
    plies = settings.coach.walkthrough_max_plies
    if len(body.line_uci) > plies:
        raise _unprocessable(f"A walkthrough covers at most {plies} moves.")
    start, fens = _replay(game, body, settings)
    _check_not_withheld(session, settings, game, start, body.line_uci[0])

    cached = load_walkthrough(session, user.id, start.fen, body.line_uci)
    if cached is not None:
        ready = Walkthrough.model_validate(cached.steps).model_copy(
            update={"start_path_uci": start.path_uci}
        )
        return stream_coach(_ready(ready), _events, settings, game.id)

    if walkthroughs_written(session, game.id) >= settings.coach.walkthrough_max_per_game:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You've reached the limit of walkthroughs for this game.",
        )
    results = _checked_results(body.step_results, [start.fen, *fens], settings)
    player = current_player(session, settings, user, game)
    call = build_call(user.id, game.id, start, body.line_uci, results, player)
    sessions = session_factory(request)

    async def work() -> Walkthrough:
        written = await generate(client, settings, sessions, call)
        with sessions() as db:
            save_walkthrough(
                db,
                user_id=user.id,
                game_id=game.id,
                start_path=start.path_uci,
                start_fen=start.fen,
                line_uci=body.line_uci,
                steps=written.model_dump(mode="json"),
            )
        return written

    return stream_coach(work(), _events, settings, game.id)


def _replay(
    game: Game, body: WalkthroughRequest, settings: Settings
) -> tuple[ResolvedPath, list[str]]:
    """The start position and the FEN after each move of the line (422 if anything's illegal)."""
    limits = settings.limits
    parsed = parse_pgn(game.pgn, max_chars=limits.max_pgn_chars, max_plies=limits.max_plies)
    try:
        start = resolve_path(parsed, body.start_path_uci, limits.max_plies)
        resolve_path(parsed, [*body.start_path_uci, *body.line_uci], limits.max_plies)
    except PathError as error:
        raise _unprocessable(error.message) from error
    board = chess.Board(start.fen)
    fens = []
    for uci in body.line_uci:
        board.push(chess.Move.from_uci(uci))
        fens.append(board.fen())
    return start, fens


def _check_not_withheld(
    session: Session, settings: Settings, game: Game, start: ResolvedPath, first: str
) -> None:
    """The best line of a critical moment only after it's solved or revealed (SPEC_V3 §7.1): a
    line from an unsolved moment's position that opens with a good-or-better move is refused."""
    summary = load_summary(session, game.id)
    if summary is None:
        return
    progress = load_progress(session, game.id)
    for moment in summary.moments:
        row = progress.get(moment.index)
        if row is not None and row.state in ("solved", "revealed"):
            continue
        if position_key(moment.fen_before) != position_key(start.fen):
            continue
        stored = load_position_result(session, game.id, moment.fen_before, tiers=("deep", "verify"))
        board = chess.Board(moment.fen_before)
        san = board.san(chess.Move.from_uci(first))
        if stored is None or san in good_first_moves(board, stored, settings.thresholds):
            raise HTTPException(status.HTTP_409_CONFLICT, detail=UNSOLVED)


def _checked_results(
    results: Sequence[EngineResult], fens: Sequence[str], settings: Settings
) -> dict[str, EngineResult]:
    """One checked search per position that can be searched (checkmate and stalemate are
    scored from the board), keyed by the replayed FEN."""
    tiers: dict[Tier, EngineTier] = {
        "scan": settings.engine.scan,
        "verify": settings.engine.verify,
        "deep": settings.engine.deep,
    }
    by_key = {position_key(r.fen): r for r in results}
    checked: dict[str, EngineResult] = {}
    for fen in fens:
        if terminal_evaluation(chess.Board(fen)) is not None:
            continue
        result = by_key.get(position_key(fen))
        if result is None:
            raise _unprocessable(NEEDS_SCAN)
        try:
            checked[fen] = check_for_position(result, fen=fen, tier_configs=tiers)
        except EngineResultError as error:
            raise _unprocessable(error.message) from error
    return checked


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


async def _ready(result: Walkthrough) -> Walkthrough:
    return result


def _events(result: Walkthrough) -> list[str]:
    return [
        sse.event("walkthrough", result.model_dump(mode="json")),
        sse.event("done", {"invalid_moves_removed": result.invalid_moves_removed}),
    ]
