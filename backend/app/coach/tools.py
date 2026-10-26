"""The analyze_position tool (SPEC §8.2): input validation and the result the coach receives.

The coach never evaluates a move itself; it asks for an engine analysis, which the browser runs
(deep tier) and the backend turns into this result.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import chess
from anthropic.types import ToolParam
from pydantic import BaseModel

from app.analysis.classify import Classification, classify
from app.analysis.engine import EngineResult, uci_line_to_san
from app.analysis.evals import (
    Color,
    Evaluation,
    for_color,
    format_eval,
    terminal_evaluation,
    winning_chances,
)
from app.analysis.pgn import ParsedGame
from app.analysis.summary_models import LineSummary
from app.coach.payload import movetext
from app.config import Thresholds

ANALYZE_POSITION: ToolParam = {
    "name": "analyze_position",
    "description": (
        "Ask the chess engine to analyze a position from this game, optionally after a "
        "candidate move the player suggests. Use when the user asks about a move or idea not "
        "covered by the analysis you already have."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ply": {
                "type": "integer",
                "description": "Analyze the position before this ply (1 = White's first move).",
            },
            "candidate_move_san": {
                "type": "string",
                "description": "Optional move the player is asking about, in SAN.",
            },
        },
        "required": ["ply"],
    },
}


class ToolInputError(Exception):
    """The tool call can't be run; `message` goes back to the coach as the tool error."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EnginePosition(BaseModel):
    fen: str
    label: Literal["position", "after_candidate"]


@dataclass(frozen=True)
class PositionRequest:
    ply: int
    fen: str
    candidate_san: str | None
    after_candidate_fen: str | None
    # A candidate that mates or stalemates is scored from the board, not searched.
    after_candidate_terminal: Evaluation | None

    def positions(self) -> list[EnginePosition]:
        positions = [EnginePosition(fen=self.fen, label="position")]
        if self.after_candidate_fen is not None:
            positions.append(EnginePosition(fen=self.after_candidate_fen, label="after_candidate"))
        return positions


def parse_tool_input(raw: object, game: ParsedGame) -> PositionRequest:
    if not isinstance(raw, Mapping):
        raise ToolInputError("The tool input must be an object with a 'ply'.")
    ply = raw.get("ply")
    last = len(game.positions) + 1
    if not isinstance(ply, int) or isinstance(ply, bool) or not 1 <= ply <= last:
        raise ToolInputError(f"ply must be a whole number from 1 to {last} (the final position).")
    fen = game.positions[ply - 1].fen_before if ply <= len(game.positions) else game.final_fen
    board = chess.Board(fen)
    if terminal_evaluation(board) is not None:
        raise ToolInputError(
            "The game is already over in that position; there is nothing to analyze."
        )

    candidate = raw.get("candidate_move_san")
    if candidate is None or (isinstance(candidate, str) and not candidate.strip()):
        return PositionRequest(ply, fen, None, None, None)
    if not isinstance(candidate, str):
        raise ToolInputError("candidate_move_san must be a move in SAN, like Nf3.")
    side = "White" if board.turn == chess.WHITE else "Black"
    try:
        move = board.parse_san(candidate.strip())
    except ValueError as error:
        raise ToolInputError(
            f"{candidate.strip()} is not a legal move in that position ({side} to move)."
        ) from error
    san = board.san(move)
    board.push(move)
    terminal = terminal_evaluation(board)
    return PositionRequest(ply, fen, san, None if terminal else board.fen(), terminal)


class CandidateResult(BaseModel):
    move_san: str
    eval_after: str
    # How the candidate compares with the engine's best move, for the side that would play it.
    classification_if_played: Classification | None
    is_best_move: bool
    best_replies: list[LineSummary]  # the opponent's best answers to the candidate


class AnalysisToolResult(BaseModel):
    ply: int
    move_number: int
    side_to_move: Color
    moves_before: str  # the game's moves up to this position
    played_in_game: str | None  # the move actually played here
    eval: str
    best_lines: list[LineSummary]
    candidate: CandidateResult | None
    depth: int


def build_tool_result(
    request: PositionRequest,
    game: ParsedGame,
    results_by_fen: Mapping[str, EngineResult],
    thresholds: Thresholds,
) -> AnalysisToolResult:
    """Turn the browser's deep-dive results into what the coach is told."""
    root = results_by_fen[request.fen]
    mover: Color = "white" if request.fen.split()[1] == "w" else "black"
    candidate = None
    if request.candidate_san is not None:
        candidate = _candidate(request, root, results_by_fen, mover, thresholds)
    played = game.positions[request.ply - 1].san if request.ply <= len(game.positions) else None
    return AnalysisToolResult(
        ply=request.ply,
        move_number=(request.ply + 1) // 2,
        side_to_move=mover,
        moves_before=movetext(game.positions[: request.ply - 1]),
        played_in_game=played,
        eval=format_eval(root.evaluation()),
        best_lines=line_summaries(request.fen, root),
        candidate=candidate,
        depth=root.depth,
    )


def line_summaries(fen: str, result: EngineResult) -> list[LineSummary]:
    return [
        LineSummary(
            rank=line.rank,
            eval=format_eval(line.evaluation()),
            moves_san=uci_line_to_san(fen, line.moves_uci),
        )
        for line in result.lines
    ]


def _candidate(
    request: PositionRequest,
    root: EngineResult,
    results_by_fen: Mapping[str, EngineResult],
    mover: Color,
    thresholds: Thresholds,
) -> CandidateResult:
    assert request.candidate_san is not None
    replies: list[LineSummary] = []
    if request.after_candidate_terminal is not None:
        eval_after = request.after_candidate_terminal
    else:
        assert request.after_candidate_fen is not None
        after = results_by_fen[request.after_candidate_fen]
        eval_after = after.evaluation()
        replies = line_summaries(request.after_candidate_fen, after)
    best_san = uci_line_to_san(request.fen, root.lines[0].moves_uci[:1])[0]
    drop = for_color(winning_chances(root.evaluation()) - winning_chances(eval_after), mover)
    return CandidateResult(
        move_san=request.candidate_san,
        eval_after=format_eval(eval_after),
        classification_if_played=classify(drop, thresholds),
        is_best_move=request.candidate_san == best_san,
        best_replies=replies,
    )
