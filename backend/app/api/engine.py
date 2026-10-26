"""Engine routes: tier settings for the browser, and scan/verify result submission (SPEC §9)."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.analysis.engine import (
    EngineResult,
    EngineResultError,
    Tier,
    best_by_fen,
    check_batch,
    position_evaluations,
)
from app.analysis.evals import Color
from app.analysis.pgn import ParsedGame, parse_pgn
from app.analysis.selection import scan_fens, select_verify_plies, verify_fens
from app.analysis.summary import build_summary
from app.analysis.summary_models import UserInfo
from app.api.deps import get_app_settings, get_session
from app.api.schemas import EngineResultsRequest, ScanResponse, VerifyResponse
from app.api.scoping import OwnedGame
from app.auth.deps import CurrentUser
from app.config import EngineSettings, Settings
from app.db.engine_results import load_results, save_results, save_summary
from app.db.models import Game

router = APIRouter(prefix="/api", tags=["engine"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@router.get("/engine-config")
def engine_config(_user: CurrentUser, settings: SettingsDep) -> EngineSettings:
    return settings.engine


@router.post("/games/{game_id}/engine/scan")
def submit_scan(
    game: OwnedGame, body: EngineResultsRequest, session: SessionDep, settings: SettingsDep
) -> ScanResponse:
    parsed = _parse(game, settings)
    results = _check(body.results, "scan", settings, scan_fens(parsed))
    save_results(session, game.id, results)
    if game.status == "uploaded":
        game.status = "scanned"
        session.commit()
    return ScanResponse(verify_fens=_verify_fens(parsed, game, results, settings))


@router.post("/games/{game_id}/engine/verify")
def submit_verify(
    game: OwnedGame, body: EngineResultsRequest, session: SessionDep, settings: SettingsDep
) -> VerifyResponse:
    parsed = _parse(game, settings)
    scan_results = load_results(session, game.id, ["scan"])
    if not scan_results:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Submit the scan results first.")
    expected = _verify_fens(parsed, game, scan_results, settings)
    results = _check(body.results, "verify", settings, expected)
    save_results(session, game.id, results)

    user = UserInfo(color=cast(Color, game.user_color), elo=game.elo, playstyle=game.playstyle)
    all_results = load_results(session, game.id, ["scan", "verify"])
    summary = build_summary(parsed, all_results, user, settings)
    save_summary(session, game.id, summary)
    game.status = "analyzed"
    session.commit()
    return VerifyResponse(summary_ready=True, counts=summary.counts, accuracy=summary.accuracy)


def _parse(game: Game, settings: Settings) -> ParsedGame:
    # The stored PGN was validated on upload, so re-parsing it can't fail.
    return parse_pgn(
        game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
    )


def _check(
    results: list[EngineResult], tier: Tier, settings: Settings, expected: list[str]
) -> list[EngineResult]:
    try:
        return check_batch(
            results,
            tier=tier,
            tier_config=getattr(settings.engine, tier),
            expected_fens=expected,
        )
    except EngineResultError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message) from error


def _verify_fens(
    parsed: ParsedGame, game: Game, scan_results: list[EngineResult], settings: Settings
) -> list[str]:
    evals = position_evaluations(parsed, best_by_fen(scan_results))
    user_color = cast(Color, game.user_color)  # validated on upload
    return verify_fens(parsed, select_verify_plies(evals, user_color, settings.thresholds))
