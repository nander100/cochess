"""PGN export (SPEC_V3 §5.2): the game as played, with the player's saved variations, NAGs on the
player's mistakes, the engine's evaluation after every move, and a note at each critical moment.

Everything comes from stored data; nothing is re-analyzed. The export is for after the player has
finished with the game, so critical moments always name the best move.
"""

import io
import re
from collections.abc import Mapping, Sequence

import chess
import chess.engine
import chess.pgn
from pydantic import BaseModel, ConfigDict

from app.analysis.evals import Color, Evaluation
from app.analysis.summary_models import MoveLabel
from app.analysis.variations import SavedVariation

NAGS: Mapping[MoveLabel, int] = {
    "inaccuracy": chess.pgn.NAG_DUBIOUS_MOVE,  # ?!
    "mistake": chess.pgn.NAG_MISTAKE,  # ?
    "blunder": chess.pgn.NAG_BLUNDER,  # ??
    "missed_mate": chess.pgn.NAG_MISTAKE,  # ?
}

_LABEL_WORDS: Mapping[MoveLabel, str] = {
    "inaccuracy": "an inaccuracy",
    "mistake": "a mistake",
    "blunder": "a blunder",
    "missed_mate": "a missed forced mate",
}

_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class ExportMoment(BaseModel):
    """A critical moment as the export notes it."""

    model_config = ConfigDict(frozen=True)

    ply: int
    label: MoveLabel
    best_san: str | None  # None if the engine result for the position is missing


def export_pgn(
    stored_pgn: str,
    *,
    user_color: Color,
    evals: Sequence[Evaluation] | None,
    labels: Mapping[int, MoveLabel | None],
    moments: Sequence[ExportMoment],
    variations: Sequence[SavedVariation],
) -> str:
    """The annotated PGN. `stored_pgn` is the game's clean main line (headers and clocks kept);
    `evals[ply]` is the position after `ply` (0 = the start), as GameDetail uses them."""
    game = chess.pgn.read_game(io.StringIO(stored_pgn))
    if game is None:
        raise ValueError("stored PGN has no game")
    if "Annotator" not in game.headers:
        game.headers["Annotator"] = "CoChess"
    notes = {moment.ply: _moment_note(moment) for moment in moments}
    user_parity = 1 if user_color == "white" else 0

    for ply, node in enumerate(game.mainline(), start=1):
        label = labels.get(ply)
        if label is not None and ply % 2 == user_parity:
            node.nags.add(NAGS[label])
        if ply in notes:
            node.comment = f"{node.comment} {notes[ply]}".strip()
        if evals is not None and ply < len(evals):
            score = _score(evals[ply])
            if score is not None:
                node.set_eval(score)

    for variation in variations:
        _add_line(game, [*variation.start_path, *variation.moves])

    return str(game) + "\n"


def export_filename(headers: Mapping[str, str]) -> str:
    """ "White-vs-Black-2026.10.20.pgn", with anything unsafe in a filename replaced."""
    parts = [headers.get("White", "White"), "vs", headers.get("Black", "Black")]
    date = headers.get("Date", "")
    if date and "?" not in date:
        parts.append(date)
    name = _FILENAME_UNSAFE.sub("_", "-".join(parts)).strip("._-") or "game"
    return f"{name}.pgn"


def _moment_note(moment: ExportMoment) -> str:
    note = f"Critical moment: {_LABEL_WORDS[moment.label]}."
    return f"{note} Best was {moment.best_san}." if moment.best_san else note


def _score(evaluation: Evaluation) -> chess.engine.PovScore | None:
    if evaluation.cp is not None:
        return chess.engine.PovScore(chess.engine.Cp(evaluation.cp), chess.WHITE)
    if evaluation.mate is not None:
        return chess.engine.PovScore(chess.engine.Mate(evaluation.mate), chess.WHITE)
    return None  # already checkmate: the result says it


def _add_line(game: chess.pgn.Game, path: Sequence[str]) -> None:
    """Follow `path` from the start, reusing moves already in the tree and adding the rest as
    variations (after the game's own move, so the main line stays the game)."""
    node: chess.pgn.GameNode = game
    for uci in path:
        move = chess.Move.from_uci(uci)
        node = node.variation(move) if node.has_variation(move) else node.add_variation(move)
