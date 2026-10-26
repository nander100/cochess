"""Generate a real synopsis for an owner fixture game (M4 checkpoint evidence).

Usage (from backend/): uv run python -m scripts.synopsis game5b --elo 800 [--playstyle "..."]
    [--model claude-sonnet-5-5] [--effort low]
Calls the real Claude API with ANTHROPIC_API_KEY from .env, through the same service the
endpoint uses (validation, regeneration, usage logging), on an in-memory database.
"""

import argparse
import asyncio
import sys

from app.analysis.summary_models import UserInfo
from app.coach.client import AnthropicCoachClient
from app.coach.service import generate_synopsis
from app.config import Effort, Settings
from app.db.engine_results import save_summary
from app.db.models import Game, LlmUsageRow
from app.main import create_app
from scripts.print_summary import FIXTURES, summary_for

# USD per million tokens (input, output, cache read, cache write), from the public price list;
# for estimates only. Haiku 5.5 is listed "from" these prices.
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}


def estimated_cost(usage: LlmUsageRow) -> float | None:
    price = PRICES.get(usage.model)
    if price is None:
        return None
    tokens = (
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usage.cache_write_tokens,
    )
    return sum(n * p for n, p in zip(tokens, price, strict=True)) / 1_000_000


async def run(
    game: str, elo: int, playstyle: str | None, model: str | None, effort: Effort | None
) -> None:
    base = Settings(database_url="sqlite://")
    coach = base.coach.model_copy(update={"synopsis_effort": effort}) if effort else base.coach
    settings = base.model_copy(
        update={"coach_model_synopsis": model or base.coach_model_synopsis, "coach": coach}
    )
    if not settings.anthropic_api_key:
        sys.exit("Set ANTHROPIC_API_KEY in backend/.env first.")
    app = create_app(settings)
    summary = summary_for(game, elo)
    summary = summary.model_copy(
        update={"user": UserInfo(color=summary.user.color, elo=elo, playstyle=playstyle)}
    )
    pgn = next((FIXTURES / "pgn" / "user").glob(f"{game}.*")).read_text()
    sessions = app.state.session_factory
    with sessions() as session:
        row = Game(pgn=pgn, user_color=summary.user.color, elo=elo, playstyle=playstyle, headers={})
        session.add(row)
        session.commit()
        game_id = row.id
        save_summary(session, game_id, summary)

    client = AnthropicCoachClient(settings.anthropic_api_key)
    result = await generate_synopsis(client, settings, sessions, game_id)

    out = sys.stdout
    out.write(
        f"===== {game} as {summary.user.color}, Elo {elo}, {settings.coach_model_synopsis} "
        f"at {settings.coach.synopsis_effort} effort\n\n{result.text}\n\n"
    )
    out.write(f"words: {len(result.text.split())}\n")
    out.write(f"moves removed after validation: {result.invalid_moves_removed or 'none'}\n")
    with sessions() as session:
        for usage in session.query(LlmUsageRow).order_by(LlmUsageRow.id):
            out.write(
                f"usage: {usage.model} in={usage.input_tokens} out={usage.output_tokens} "
                f"cache_read={usage.cache_read_tokens} cache_write={usage.cache_write_tokens}"
                f" ~${estimated_cost(usage) or 0:.4f}\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game")
    parser.add_argument("--elo", type=int, required=True)
    parser.add_argument("--playstyle", default=None)
    parser.add_argument("--model", default=None, help="override COACH_MODEL_SYNOPSIS")
    parser.add_argument("--effort", default=None, choices=["low", "medium", "high", "xhigh", "max"])
    args = parser.parse_args()
    asyncio.run(run(args.game, args.elo, args.playstyle, args.model, args.effort))


if __name__ == "__main__":
    main()
