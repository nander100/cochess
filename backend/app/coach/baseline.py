"""The baseline report after onboarding (SPEC_V2 §10.4): one call over all 12 games, validated
against the moves in that data, then stored for the profile."""

import logging
from dataclasses import dataclass, replace
from typing import cast

from anthropic.types import MessageParam
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.evals import Color
from app.analysis.summary_models import GameSummary, KeyMoment
from app.coach.client import CoachClient, CoachReply, CoachRequest, system_blocks
from app.coach.payload import (
    BaselineGame,
    BaselinePayload,
    CoachPayload,
    coach_view,
    profile_player,
    render,
    with_tendencies,
)
from app.coach.validate import allowed_moves, find_invalid, strip_moves
from app.config import Settings
from app.db.coach import record_usage
from app.db.engine_results import load_summary
from app.db.models import Game, User
from app.db.onboarding import onboarding_games, save_report
from app.db.tendencies import latest_tendencies

logger = logging.getLogger(__name__)

INSTRUCTION = (
    "Here are the player's 12 onboarding games, analyzed by the engine, with their tendencies "
    "across games, as JSON. Write the baseline report described in your instructions."
)
REGENERATE_NOTE = (
    "Your report mentioned moves that are not in the data: {moves}. Rewrite the complete report. "
    "Only write moves exactly as they appear in the JSON, and describe pieces and squares in words."
)
OPENING_PLIES = 8
_PRIORITY = {"missed_mate": 0, "blunder": 1, "mistake": 2, "inaccuracy": 3}


@dataclass(frozen=True)
class BaselineResult:
    text: str
    invalid_moves_removed: list[str]
    game_ids: list[str]


def build_baseline_payload(
    user: User, games: list[tuple[Game, GameSummary]], session: Session, settings: Settings
) -> CoachPayload:
    """The profile, tendencies and accuracy, and a compact summary of each game, oldest first."""
    elo = user.elo if user.elo is not None else games[0][0].elo
    player = with_tendencies(
        profile_player(elo, user.playstyle, None),
        latest_tendencies(session, user.id),
        settings.tendencies,
    )
    ordered = sorted(games, key=lambda pair: pair[0].played_at or pair[0].created_at)
    return CoachPayload(
        task="baseline_report",
        player=player,
        baseline=BaselinePayload(
            games=[
                _game(number, game, summary, settings)
                for number, (game, summary) in enumerate(ordered, start=1)
            ]
        ),
    )


def _game(number: int, game: Game, summary: GameSummary, settings: Settings) -> BaselineGame:
    color = cast(Color, game.user_color)
    view = coach_view(summary, settings.coach)
    opening = summary.move_list[:OPENING_PLIES]
    return BaselineGame(
        number=number,
        date=(game.played_at or game.created_at).date().isoformat(),
        opponent=summary.game.black if color == "white" else summary.game.white,
        color=color,
        result="win" if game.user_result == "win" else "loss",
        opening=summary.game.opening,
        opening_moves=" ".join(
            f"{m.move_number}. {m.san}" if m.side == "white" else m.san for m in opening
        ),
        accuracy=summary.accuracy.user,
        opening_accuracy=summary.phase_breakdown["opening"].accuracy,
        counts=summary.counts,
        key_moments=_worst(view.key_moments, color, settings.coach.baseline_moments_per_game),
    )


def _worst(moments: list[KeyMoment], color: Color, limit: int) -> list[KeyMoment]:
    """The player's own labeled moments, worst first, then back in game order."""
    own = [m for m in moments if m.side == color and m.classification is not None]
    worst = sorted(own, key=lambda m: (_PRIORITY[m.classification or "inaccuracy"], m.ply))
    return sorted(worst[:limit], key=lambda m: m.ply)


async def generate_baseline(
    client: CoachClient, settings: Settings, sessions: sessionmaker[Session], user_id: str
) -> BaselineResult:
    """Write the report, regenerate once if it names moves not in the data, strip any that
    remain (SPEC §7.4), and store it."""
    with sessions() as session:
        user = session.get(User, user_id)
        if user is None:
            raise LookupError(f"user {user_id} not found")
        games = []
        for game in onboarding_games(session, user_id):
            summary = load_summary(session, game.id)
            if summary is None:
                raise LookupError(f"onboarding game {game.id} has no summary yet")
            games.append((game, summary))
        payload = build_baseline_payload(user, games, session, settings)
    allowed = allowed_moves(payload.model_dump(mode="json"))
    messages: list[MessageParam] = [{"role": "user", "content": render(payload, INSTRUCTION)}]
    request = CoachRequest(
        model=settings.coach_model_synopsis,
        system=system_blocks("baseline_report"),
        messages=messages,
        max_tokens=settings.coach.baseline_max_tokens,
        effort=settings.coach.baseline_effort,
    )

    reply = await _call(client, request, sessions, user_id)
    invalid = find_invalid(reply.text, allowed)
    if invalid:
        retry: list[MessageParam] = [
            *messages,
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": REGENERATE_NOTE.format(moves=", ".join(invalid))},
        ]
        reply = await _call(client, replace(request, messages=retry), sessions, user_id)
        invalid = find_invalid(reply.text, allowed)

    text = reply.text
    if invalid:
        text = strip_moves(text, invalid)
        logger.warning("coach moves removed: user=%s endpoint=baseline moves=%s", user_id, invalid)
    words = len(text.split())
    if words > settings.coach.baseline_max_words:
        logger.warning("baseline report too long: user=%s words=%d", user_id, words)
    game_ids = [game.id for game, _ in games]
    with sessions() as session:
        save_report(session, user_id, text, invalid, game_ids)
    return BaselineResult(text=text, invalid_moves_removed=invalid, game_ids=game_ids)


async def _call(
    client: CoachClient, request: CoachRequest, sessions: sessionmaker[Session], user_id: str
) -> CoachReply:
    reply = await client.complete(request)
    with sessions() as session:
        record_usage(session, None, "baseline_report", reply.model, reply.usage, user_id=user_id)
    return reply
