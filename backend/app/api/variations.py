"""Saved variations and PGN export (SPEC_V3 §5). Both are scoped to the player's own games."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.analysis.engine import best_by_fen, position_evaluations, uci_line_to_san
from app.analysis.pgn import ParsedGame, parse_pgn
from app.analysis.pgn_export import ExportMoment, export_filename, export_pgn
from app.analysis.variations import VariationError, check_variations
from app.api.deps import get_app_settings, get_session
from app.api.schemas import SaveVariationsRequest, VariationsResponse
from app.api.scoping import OwnedGame
from app.config import Settings
from app.db.engine_results import load_results, load_summary
from app.db.models import Game
from app.db.variations import load_variations, save_variations

router = APIRouter(prefix="/api/games", tags=["variations"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@router.get("/{game_id}/variations")
def get_variations(game: OwnedGame, session: SessionDep) -> VariationsResponse:
    saved = load_variations(session, game)
    return VariationsResponse(variations=saved or [], saved=saved is not None)


@router.put("/{game_id}/variations")
def put_variations(
    game: OwnedGame, body: SaveVariationsRequest, session: SessionDep, settings: SettingsDep
) -> VariationsResponse:
    """Replace the player's variations for this game with the list sent, in its order. Every
    variation is replayed first; one bad move rejects the whole save (422)."""
    parsed = _parsed(game, settings)
    try:
        kept = check_variations(parsed, body.variations, settings.limits)
    except VariationError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message) from error
    if game.user_id is None:  # unreachable: OwnedGame only returns the player's own games
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    save_variations(session, game, game.user_id, kept)
    return VariationsResponse(variations=kept, saved=True)


@router.get("/{game_id}/export.pgn")
def export_game(game: OwnedGame, session: SessionDep, settings: SettingsDep) -> Response:
    """The game as an annotated PGN download (SPEC_V3 §5.2)."""
    parsed = _parsed(game, settings)
    by_fen = best_by_fen(load_results(session, game.id, ["scan", "verify", "deep"]))
    try:
        evals = position_evaluations(parsed, dict(by_fen))
    except KeyError:
        evals = None  # not fully scanned yet: export without evaluations
    summary = load_summary(session, game.id)
    moments = []
    for moment in summary.moments if summary else []:
        result = by_fen.get(moment.fen_before)
        best = (
            uci_line_to_san(moment.fen_before, [result.lines[0].moves_uci[0]])[0]
            if result is not None and result.lines
            else None
        )
        moments.append(ExportMoment(ply=moment.ply, label=moment.label, best_san=best))
    text = export_pgn(
        game.pgn,
        user_color="white" if game.user_color == "white" else "black",
        evals=evals,
        labels={move.ply: move.classification for move in summary.move_list} if summary else {},
        moments=moments,
        variations=load_variations(session, game) or [],
    )
    filename = export_filename(parsed.headers)
    return Response(
        content=text,
        media_type="application/x-chess-pgn",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parsed(game: Game, settings: Settings) -> ParsedGame:
    return parse_pgn(
        game.pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
    )
