"""The JSON payload sent to the coach (SPEC §7.2)."""

import json
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from app.analysis.evals import Color
from app.analysis.pgn import ParsedGame, Position
from app.analysis.summary_models import GameSummary, LineSummary

RatingBand = Literal["beginner", "intermediate", "advanced"]
Task = Literal["synopsis", "chat"]

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
    tendencies: list[str] = []  # cross-game tracking is v2; the field keeps the schema stable


class CoachPayload(BaseModel):
    task: Task
    user_prompt: str | None = None
    player: PlayerPayload
    pgn_to_move: str | None = None  # chat turns leave it out: the game is in the cached context
    fen: str | None = None
    engine_lines: list[LineSummary] | None = None
    game_summary: GameSummary | None = None


def rating_band(elo: int) -> RatingBand:
    if elo < BEGINNER_BELOW:
        return "beginner"
    return "intermediate" if elo <= ADVANCED_ABOVE else "advanced"


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


def build_synopsis_payload(summary: GameSummary, game: ParsedGame) -> CoachPayload:
    """The full game and its summary; `fen` and `engine_lines` are omitted (SPEC §7.2)."""
    return CoachPayload(
        task="synopsis",
        player=player_payload(summary),
        pgn_to_move=movetext(game.positions),
        game_summary=summary,
    )


def render(payload: CoachPayload, instruction: str) -> str:
    """The user turn: a short instruction line, then the payload JSON.

    The eval curve duplicates `move_list[].eval_after`, so it's left out to save tokens (PLAN Q28).
    """
    data = payload.model_dump(
        mode="json", exclude_none=True, exclude={"game_summary": {"eval_curve"}}
    )
    return f"{instruction}\n\n{json.dumps(data, separators=(',', ':'))}"
