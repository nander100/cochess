"""Print the game summary for an owner fixture game from its captured engine results.

Usage (from backend/): uv run python -m scripts.print_summary game1w [--elo 1400] [--compact]
Engine results come from tests/fixtures/engine/<game>.json, captured by `npm run e2e`.
"""

import argparse
import json
import sys
from pathlib import Path

from app.analysis.engine import EngineResult
from app.analysis.pgn import parse_pgn
from app.analysis.summary import build_summary
from app.analysis.summary_models import GameSummary, UserInfo
from app.config import Settings

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def summary_for(game: str, elo: int | None = None) -> GameSummary:
    settings = Settings(_env_file=None)
    pgn = next((FIXTURES / "pgn" / "user").glob(f"{game}.*")).read_text()
    engine = json.loads((FIXTURES / "engine" / f"{game}.json").read_text())
    parsed = parse_pgn(
        pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
    )
    color = engine["user_color"]
    rating = elo or int(parsed.headers.get("WhiteElo" if color == "white" else "BlackElo", 1200))
    results = [EngineResult.model_validate(r) for r in engine["scan"] + engine["verify"]]
    return build_summary(
        parsed, results, UserInfo(color=color, elo=rating, playstyle=None), settings
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", help="fixture name, e.g. game1w")
    parser.add_argument("--elo", type=int, default=None)
    parser.add_argument("--compact", action="store_true", help="omit eval_curve and move_list")
    args = parser.parse_args()
    exclude = {"eval_curve", "move_list"} if args.compact else None
    summary = summary_for(args.game, args.elo)
    sys.stdout.write(summary.model_dump_json(indent=2, exclude=exclude) + "\n")


if __name__ == "__main__":
    main()
