"""Line playback (SPEC_V3 §9.5, §9.6): `POST /api/lines/{line_id}/playback` with the browser's
scan of each position of a linked line. The backend checks the scans against the replayed line
and decides where playback stops and what the caption says; the LLM has no part in it. A
position without a scan counts as unknown (material still decides), so playback can start
before the background scan finishes."""

from collections.abc import Sequence
from typing import Annotated

import chess
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analysis.engine import EngineResult, EngineResultError, Tier, check_for_position
from app.analysis.evals import Evaluation, format_eval, terminal_evaluation, win_percent
from app.analysis.paths import PathError, position_key, resolve_path
from app.analysis.pgn import parse_pgn
from app.analysis.settle import settle
from app.api.deps import get_app_settings, get_session
from app.auth.deps import CurrentUser
from app.config import EngineTier, Settings
from app.db.line_links import load_line_link
from app.db.models import Game, LineLinkRow

router = APIRouter(prefix="/api/lines", tags=["lines"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
MAX_POSITIONS = 11  # the start and one after each of at most 10 moves
AFTER_A_TRY = ("refutation", "candidate")  # the player's move first: two more plies are shown


class PlaybackRequest(BaseModel):
    step_results: list[EngineResult] = Field(default_factory=list, max_length=MAX_POSITIONS)


class Playback(BaseModel):
    line_id: str
    start_fen: str
    moves_uci: list[str]
    moves_san: list[str]
    evals: list[str | None]  # the start, then after each move; "+0.3", "-M2"
    win_pcts: list[float | None]  # White's, for the eval bar
    settle_ply: int  # stop after this many moves (SPEC_V3 §9.6)
    caption: str  # what changed by then, in words, from the boards


@router.post("/{line_id}/playback")
def playback(
    line_id: str,
    body: PlaybackRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> Playback:
    row = load_line_link(session, user.id, line_id)
    game = session.get(Game, row.game_id) if row is not None else None
    if row is None or game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="That line was not found.")
    fens, sans = _replay(game, row, settings)
    evals = _evals(body.step_results, fens, settings)
    plies = (
        settings.playback.settle_min_plies_after_try
        if row.kind in AFTER_A_TRY
        else settings.playback.settle_min_plies
    )
    settled = settle(fens[0], row.moves, evals, plies, settings.playback)
    shown = [format_eval(e) if e is not None else None for e in evals]
    row.step_evals, row.settle_ply, row.caption = shown, settled.settle_ply, settled.caption
    session.commit()
    return Playback(
        line_id=row.id,
        start_fen=fens[0],
        moves_uci=list(row.moves),
        moves_san=sans,
        evals=shown,
        win_pcts=[win_percent(e) if e is not None else None for e in evals],
        settle_ply=settled.settle_ply,
        caption=settled.caption,
    )


def _replay(game: Game, row: LineLinkRow, settings: Settings) -> tuple[list[str], list[str]]:
    """The FEN of the start and of each position along the line, and the line's SAN."""
    limits = settings.limits
    parsed = parse_pgn(game.pgn, max_chars=limits.max_pgn_chars, max_plies=limits.max_plies)
    try:
        start = resolve_path(parsed, row.start_path, limits.max_plies)
    except PathError as error:  # stored lines are checked when written; this is a safety net
        raise HTTPException(status.HTTP_409_CONFLICT, detail=error.message) from error
    board = chess.Board(start.fen)
    fens, sans = [start.fen], []
    for uci in row.moves:
        move = chess.Move.from_uci(uci)
        sans.append(board.san(move))
        board.push(move)
        fens.append(board.fen())
    return fens, sans


def _evals(
    results: Sequence[EngineResult], fens: Sequence[str], settings: Settings
) -> list[Evaluation | None]:
    tiers: dict[Tier, EngineTier] = {
        "scan": settings.engine.scan,
        "verify": settings.engine.verify,
        "deep": settings.engine.deep,
    }
    wanted = {position_key(fen): fen for fen in fens}
    checked: dict[str, Evaluation] = {}
    for result in results:
        fen = wanted.get(position_key(result.fen))
        if fen is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="An engine result is for a position that isn't on this line.",
            )
        try:
            checked[fen] = check_for_position(result, fen=fen, tier_configs=tiers).evaluation()
        except EngineResultError as error:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message
            ) from error
    return [terminal_evaluation(chess.Board(fen)) or checked.get(fen) for fen in fens]
