"""The JSON payload sent to the coach (SPEC §7.2)."""

import json
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from app.analysis.evals import Color
from app.analysis.moments import Hint
from app.analysis.pgn import Position
from app.analysis.phase import Phase
from app.analysis.summary_models import Counts, GameSummary, KeyMoment, LineSummary, MoveLabel
from app.analysis.tendencies import Example, TendencyReport, Trend
from app.config import CoachSettings, TendencySettings

RatingBand = Literal["beginner", "intermediate", "advanced"]
Task = Literal["synopsis", "chat", "explain", "moment_intro", "moment_feedback", "baseline_report"]

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


class PlayerTendency(BaseModel):
    """SPEC_V2 §9.3. `recent_example`'s move counts as an allowed move for validation."""

    theme: str
    label: str
    rate_per_game: float
    trend: Trend | None
    games_seen: int
    provisional: bool
    recent_example: Example


class PlayerPayload(BaseModel):
    elo: int
    color: Color | None  # the side they played; None for the baseline report (both colors)
    rating_band: RatingBand
    playstyle: str | None
    # Across the player's analyzed games (SPEC_V2 §9.3): the top themes, then accuracy.
    tendencies: list[PlayerTendency] = []
    accuracy_by_phase: dict[Phase, float | None] | None = None
    accuracy_by_color: dict[Color, float | None] | None = None


class PositionPayload(BaseModel):
    """What's on the player's board (SPEC_V2 §6.1), replayed by the backend from the path."""

    path_san: list[str]
    pgn_to_move: str
    fen: str
    ply: int
    on_mainline: bool
    branch_ply: int | None  # where the player left the game, if they did
    variation_san: list[str]


class MomentGameMove(BaseModel):
    """The move the player made in the game: theirs to learn from, so always shown."""

    san: str  # with its move number, e.g. "12...Nxf6"
    classification: MoveLabel
    eval_before: str
    eval_after: str
    themes: list[str]
    refutation_san: list[str]  # what the engine shows goes wrong after it


class MomentCandidate(BaseModel):
    """The player's latest attempt, graded by the engine (SPEC_V2 §8.3)."""

    san: str
    grade: str  # best / good / inaccuracy / mistake / blunder
    eval_after: str
    themes: list[str]
    refutation_san: list[str]  # the engine's best reply line to the attempt


class MomentAttempt(BaseModel):
    san: str
    grade: str
    reasoning: str | None


class MomentBest(BaseModel):
    """Only once the moment is solved or revealed (SPEC_V2 §8.4)."""

    san: str
    eval: str
    lines: list[LineSummary]


class MomentResult(BaseModel):
    """One moment's outcome, for the wrap-up."""

    index: int
    game_move: str
    outcome: Literal["solved", "revealed"]
    attempts: int


class MomentPayload(BaseModel):
    """SPEC_V2 §8.4. While `reveal` is false, `best` is null and the position's engine lines are
    left out of the payload altogether: the coach can't reveal what it was never given."""

    index: int
    of: int
    state: Literal["intro", "attempt", "solved", "revealed"]
    game_move: MomentGameMove
    candidate: MomentCandidate | None = None
    earlier_attempts: list[MomentAttempt] = []
    attempt_number: int
    max_attempts: int
    hints_allowed: list[Hint] = []
    same_as_game: bool = False  # the attempt was the move played in the game
    reveal: bool
    best: MomentBest | None = None
    wrap_up: bool = False
    results: list[MomentResult] = []  # the wrap-up: how every moment went


class BaselineGame(BaseModel):
    """One onboarding game, compactly (SPEC_V2 §10.4)."""

    number: int  # 1-based, oldest first: how the report refers to the game
    date: str  # YYYY-MM-DD
    opponent: str
    color: Color
    result: Literal["win", "loss"]
    opening: str | None  # from the headers
    opening_moves: str  # the first moves, e.g. "1. e4 e5 2. Nf3 Nc6"
    accuracy: float | None
    opening_accuracy: float | None
    counts: Counts
    key_moments: list[KeyMoment]  # the player's own worst moments, with engine lines


class OpeningGroup(BaseModel):
    """The player's games that start the same way, counted by the backend so the coach doesn't
    have to: White by the player's first move, Black by the first move and the player's reply."""

    color: Color
    start: str  # "1. d4", or "1. e4 c6"
    games: int
    wins: int
    losses: int
    opening_accuracy: float | None  # the games' mean
    opponents: list[str]


class BaselinePayload(BaseModel):
    games: list[BaselineGame]
    openings: list[OpeningGroup] = []


class CoachPayload(BaseModel):
    task: Task
    user_prompt: str | None = None
    player: PlayerPayload
    pgn_to_move: str | None = None  # chat turns leave it out: the game is in the cached context
    position: PositionPayload | None = None
    engine_lines: list[LineSummary] | None = None  # for `position`: top 4 lines, 10 plies
    game_summary: GameSummary | None = None
    moment: MomentPayload | None = None
    baseline: BaselinePayload | None = None


# Per-move evals and labels are already in the annotated `pgn_to_move` (PLAN Q28, cost review).
# Moments are left out too: they're taught one at a time, with their own payload (SPEC_V2 §8).
COACH_EXCLUDE = {"game_summary": {"eval_curve", "move_list", "moments"}}


def rating_band(elo: int) -> RatingBand:
    if elo < BEGINNER_BELOW:
        return "beginner"
    return "intermediate" if elo <= ADVANCED_ABOVE else "advanced"


def profile_player(elo: int, playstyle: str | None, color: Color | None) -> PlayerPayload:
    """The player as their profile says now (PLAN_V2 §6 Q5): chat and Explain talk to who the
    player is today, not who they were when the game was analyzed."""
    return PlayerPayload(elo=elo, color=color, rating_band=rating_band(elo), playstyle=playstyle)


def player_payload(summary: GameSummary) -> PlayerPayload:
    user = summary.user
    return PlayerPayload(
        elo=user.elo, color=user.color, rating_band=rating_band(user.elo), playstyle=user.playstyle
    )


def with_tendencies(
    player: PlayerPayload, report: TendencyReport | None, settings: TendencySettings
) -> PlayerPayload:
    """The player with their top tendencies and accuracy (SPEC_V2 §9.3); unchanged before any
    game has been analyzed."""
    if report is None or report.games_analyzed == 0:
        return player
    tendencies = [
        PlayerTendency.model_validate(t.model_dump(exclude={"score"}))
        for t in report.tendencies[: settings.top_n]
    ]
    return player.model_copy(
        update={
            "tendencies": tendencies,
            "accuracy_by_phase": report.accuracy.by_phase,
            "accuracy_by_color": report.accuracy.by_color,
        }
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


def build_synopsis_payload(
    summary: GameSummary, settings: CoachSettings, player: PlayerPayload | None = None
) -> CoachPayload:
    """The annotated game and its summary; `fen` and `engine_lines` are omitted (SPEC §7.2)."""
    return CoachPayload(
        task="synopsis",
        player=player or player_payload(summary),
        pgn_to_move=annotated_movetext(summary),
        game_summary=coach_view(summary, settings),
    )


def render(payload: CoachPayload, instruction: str) -> str:
    """The user turn: a short instruction line, then the payload JSON."""
    data = payload.model_dump(mode="json", exclude_none=True, exclude=COACH_EXCLUDE)
    return f"{instruction}\n\n{json.dumps(data, separators=(',', ':'))}"
