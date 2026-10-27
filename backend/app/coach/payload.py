"""The JSON payload sent to the coach (SPEC §7.2)."""

import json
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from app.analysis.evals import Color
from app.analysis.pgn import Position
from app.analysis.summary_models import GameSummary, LineSummary, MoveLabel
from app.config import CoachSettings

RatingBand = Literal["beginner", "intermediate", "advanced"]
Task = Literal["synopsis", "chat", "explain"]

# PGN-style annotations, so one compact movetext replaces the per-move list (PLAN cost review).
ANNOTATION: dict[MoveLabel, str] = {
    "inaccuracy": "?!",
    "mistake": "?",
    "blunder": "??",
    "missed_mate": "?",
}

BEGINNER_BELOW = 1000
ADVANCED_ABOVE = 1800

SYNOPSIS_INSTRUCTION = (
    "Here is the engine and detector analysis of the player's game, as JSON. "
    "Write the synopsis described in your instructions."
)


class PlayerPayload(BaseModel):
    elo: int
    color: Color
    rating_band: RatingBand
    playstyle: str | None
    tendencies: list[str] = []  # filled in by tendency tracking (SPEC_V2 §9, M5)


class PositionPayload(BaseModel):
    """What's on the player's board (SPEC_V2 §6.1), replayed by the backend from the path."""

    path_san: list[str]
    pgn_to_move: str
    fen: str
    ply: int
    on_mainline: bool
    branch_ply: int | None  # where the player left the game, if they did
    variation_san: list[str]


class CoachPayload(BaseModel):
    task: Task
    user_prompt: str | None = None
    player: PlayerPayload
    pgn_to_move: str | None = None  # chat turns leave it out: the game is in the cached context
    position: PositionPayload | None = None
    engine_lines: list[LineSummary] | None = None  # for `position`: top 4 lines, 10 plies
    game_summary: GameSummary | None = None


# Per-move evals and labels are already in the annotated `pgn_to_move` (PLAN Q28, cost review).
COACH_EXCLUDE = {"game_summary": {"eval_curve", "move_list"}}


def rating_band(elo: int) -> RatingBand:
    if elo < BEGINNER_BELOW:
        return "beginner"
    return "intermediate" if elo <= ADVANCED_ABOVE else "advanced"


def profile_player(elo: int, playstyle: str | None, color: Color) -> PlayerPayload:
    """The player as their profile says now (PLAN_V2 §6 Q5): chat and Explain talk to who the
    player is today, not who they were when the game was analyzed."""
    return PlayerPayload(elo=elo, color=color, rating_band=rating_band(elo), playstyle=playstyle)


def player_payload(summary: GameSummary) -> PlayerPayload:
    user = summary.user
    return PlayerPayload(
        elo=user.elo, color=user.color, rating_band=rating_band(user.elo), playstyle=user.playstyle
    )


def movetext(positions: Sequence[Position]) -> str:
    """Plain SAN movetext: "1. d4 d5 2. Bf4 ...". No comments or clocks."""
    parts = []
    for position in positions:
        if position.ply % 2 == 1:
            parts.append(f"{(position.ply + 1) // 2}. {position.san}")
        else:
            parts.append(position.san)
    return " ".join(parts)


def annotated_movetext(summary: GameSummary) -> str:
    """The game with each move's label as a PGN annotation: "10. d4?? Bb4 11. a3 O-O?"."""
    parts = []
    for move in summary.move_list:
        san = move.san + (ANNOTATION[move.classification] if move.classification else "")
        parts.append(f"{move.move_number}. {san}" if move.side == "white" else san)
    return " ".join(parts)


def coach_view(summary: GameSummary, settings: CoachSettings) -> GameSummary:
    """The summary as the coach sees it: key-moment lines trimmed to what explains them."""
    plies = settings.coach_line_plies
    moments = [
        moment.model_copy(
            update={
                "engine_lines": [
                    line.model_copy(update={"moves_san": line.moves_san[:plies]})
                    for line in moment.engine_lines[: settings.coach_engine_lines]
                ],
                "line_after_san": moment.line_after_san[:plies],
            }
        )
        for moment in summary.key_moments
    ]
    return summary.model_copy(update={"key_moments": moments})


def build_synopsis_payload(summary: GameSummary, settings: CoachSettings) -> CoachPayload:
    """The annotated game and its summary; `fen` and `engine_lines` are omitted (SPEC §7.2)."""
    return CoachPayload(
        task="synopsis",
        player=player_payload(summary),
        pgn_to_move=annotated_movetext(summary),
        game_summary=coach_view(summary, settings),
    )


def render(payload: CoachPayload, instruction: str) -> str:
    """The user turn: a short instruction line, then the payload JSON."""
    data = payload.model_dump(mode="json", exclude_none=True, exclude=COACH_EXCLUDE)
    return f"{instruction}\n\n{json.dumps(data, separators=(',', ':'))}"
