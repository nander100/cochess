"""The analyze_position tool (SPEC §8.2, updated by SPEC_V2 §6.2): input validation and the result
the coach receives.

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
from app.analysis.paths import ResolvedPath, movetext
from app.analysis.pgn import ParsedGame
from app.analysis.summary_models import LineSummary
from app.config import Thresholds

MAX_CANDIDATE_PLIES = 3

ANALYZE_POSITION: ToolParam = {
    "name": "analyze_position",
    "description": (
        "Ask the chess engine to analyze a position, optionally after a short sequence of moves "
        "the player suggests (their move, the reply, their next move). Use when the player asks "
        "about a move or idea the analysis you already have doesn't cover."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ply": {
                "type": "integer",
                "description": (
                    "Analyze the game's position before this ply (1 = White's first move). "
                    "Leave it out to analyze the position on the player's board right now."
                ),
            },
            "candidate_moves_san": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": MAX_CANDIDATE_PLIES,
                "description": (
                    "Optional moves to play from that position first, in SAN, in order "
                    '(up to 3 plies, e.g. ["Nxe5", "Nxe5", "dxe5"]).'
                ),
            },
        },
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
    fen: str
    # The game ply the position comes before, when it's a position from the game.
    ply: int | None
    moves_before: str  # numbered SAN of the moves leading to the position
    played_in_game: str | None  # the move the game continued with from here, if any
    candidate_sans: tuple[str, ...]
    after_candidate_fen: str | None
    # A sequence that mates or stalemates is scored from the board, not searched.
    after_candidate_terminal: Evaluation | None

    def positions(self) -> list[EnginePosition]:
        positions = [EnginePosition(fen=self.fen, label="position")]
        if self.after_candidate_fen is not None:
            positions.append(EnginePosition(fen=self.after_candidate_fen, label="after_candidate"))
        return positions


def parse_tool_input(raw: object, game: ParsedGame, board: ResolvedPath) -> PositionRequest:
    """Check a tool call. `board` is the position the player's message was sent from."""
    if not isinstance(raw, Mapping):
        raise ToolInputError("The tool input must be an object.")
    fen, ply, moves_before, played = _root(raw.get("ply"), game, board)
    root = chess.Board(fen)
    if terminal_evaluation(root) is not None:
        raise ToolInputError(
            "The game is already over in that position; there is nothing to analyze."
        )

    sans = _candidates(raw)
    after = root.copy(stack=False)
    played_sans: list[str] = []
    for san in sans:
        if terminal_evaluation(after) is not None:
            raise ToolInputError(f"The game is over before {san}; shorten the sequence.")
        side = "White" if after.turn == chess.WHITE else "Black"
        try:
            move = after.parse_san(san)
        except ValueError as error:
            where = f"after {' '.join(played_sans)}" if played_sans else "in that position"
            raise ToolInputError(f"{san} is not a legal move {where} ({side} to move).") from error
        played_sans.append(after.san(move))
        after.push(move)

    if not played_sans:
        return PositionRequest(fen, ply, moves_before, played, (), None, None)
    terminal = terminal_evaluation(after)
    return PositionRequest(
        fen,
        ply,
        moves_before,
        played,
        tuple(played_sans),
        None if terminal else after.fen(),
        terminal,
    )


def _root(
    raw_ply: object, game: ParsedGame, board: ResolvedPath
) -> tuple[str, int | None, str, str | None]:
    """(fen, game ply, moves before, game's next move) of the position to analyze."""
    if raw_ply is None:
        played = None
        if board.on_mainline and board.ply < len(game.positions):
            played = game.positions[board.ply].san
        ply = board.ply + 1 if board.on_mainline else None
        return board.fen, ply, board.pgn_to_move, played
    last = len(game.positions) + 1
    if not isinstance(raw_ply, int) or isinstance(raw_ply, bool) or not 1 <= raw_ply <= last:
        raise ToolInputError(
            f"ply must be a whole number from 1 to {last} (the final position), or left out "
            "for the position on the player's board."
        )
    before = [p.san for p in game.positions[: raw_ply - 1]]
    if raw_ply <= len(game.positions):
        position = game.positions[raw_ply - 1]
        return position.fen_before, raw_ply, movetext(before), position.san
    return game.final_fen, raw_ply, movetext(before), None


def _candidates(raw: Mapping[str, object]) -> list[str]:
    value = raw.get("candidate_moves_san")
    if value is None:
        legacy = raw.get("candidate_move_san")  # v1's single-move field, for pending v1 calls
        value = [legacy] if isinstance(legacy, str) and legacy.strip() else []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ToolInputError('candidate_moves_san must be a list of moves in SAN, like ["Nf3"].')
    sans = [v.strip() for v in value if v.strip()]
    if len(sans) > MAX_CANDIDATE_PLIES:
        raise ToolInputError(f"At most {MAX_CANDIDATE_PLIES} moves can be tried in a row.")
    return sans


class CandidateResult(BaseModel):
    moves_san: list[str]
    eval_after: str
    # How the position after the moves compares with the engine's best play, for the side to move
    # before them (null: about as good as the best move).
    classification_if_played: Classification | None
    is_best_move: bool  # the first move is the engine's top move
    best_replies: list[LineSummary]  # the engine's best continuations after the moves


class AnalysisToolResult(BaseModel):
    ply: int | None  # the game ply the position comes before; null for a variation position
    move_number: int
    side_to_move: Color
    moves_before: str  # the moves leading to this position
    played_in_game: str | None  # what the game continued with from here, if anything
    eval: str
    best_lines: list[LineSummary]
    candidate: CandidateResult | None
    depth: int


def build_tool_result(
    request: PositionRequest,
    results_by_fen: Mapping[str, EngineResult],
    thresholds: Thresholds,
) -> AnalysisToolResult:
    """Turn the browser's deep-dive results into what the coach is told."""
    root = results_by_fen[request.fen]
    board = chess.Board(request.fen)
    mover: Color = "white" if board.turn == chess.WHITE else "black"
    candidate = None
    if request.candidate_sans:
        candidate = _candidate(request, root, results_by_fen, mover, thresholds)
    return AnalysisToolResult(
        ply=request.ply,
        move_number=board.fullmove_number,
        side_to_move=mover,
        moves_before=request.moves_before,
        played_in_game=request.played_in_game,
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
        moves_san=list(request.candidate_sans),
        eval_after=format_eval(eval_after),
        classification_if_played=classify(drop, thresholds),
        is_best_move=request.candidate_sans[0] == best_san,
        best_replies=replies,
    )
