"""Compare new engine results with v3's on the owner's games (SPEC_V4 §8.1).

Usage (from backend/): uv run python -m scripts.engine_quality [--new DIR] [game1w game5b ...]

`npm run e2e:real` with new engine settings re-captures tests/fixtures/engine/<game>.json; the v3
results stay in tests/fixtures/engine/v3/. Both are run through the app's own summary (labels,
key moments, critical moments). Multi-threaded Stockfish isn't deterministic, so the bar is v3's
own run-to-run variation (owner decision, M3): a game passes when no move v3 called a blunder
stops being a mistake or blunder, and its label agreement is no lower than a re-run of v3's
settings got on that game, minus one point. Lost mistakes and changed critical moments are listed
for review. Exits 1 if any game fails.
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from app.analysis.engine import EngineResult
from app.analysis.pgn import parse_pgn
from app.analysis.summary import build_summary
from app.analysis.summary_models import GameSummary, UserInfo
from app.config import Settings

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
ENGINE = FIXTURES / "engine"
BASELINE = ENGINE / "v3"
SERIOUS = ("mistake", "blunder")
# Label agreement of a re-run of v3's own settings with v3 (PLAN_V4 M3 log); unmeasured games use
# the lowest measured. The bar is this minus one point.
V3_RERUN_AGREEMENT = {"game5b": 0.946, "game1w": 0.976, "game3w": 0.961}
SLACK = 0.01


class Quality(BaseModel):
    game: str
    same_labels: float  # share of moves whose label didn't change
    bar: float  # the lowest label agreement that passes
    lost: list[str]  # v3's mistakes and blunders that aren't one any more ("14. Nxe5 (mistake)")
    lost_blunders: list[str]
    moments_before: list[int]  # critical-moment plies
    moments_after: list[int]
    scan_s: tuple[float, float]  # v3, new
    verify_s: tuple[float, float]

    @property
    def passed(self) -> bool:
        return not self.lost_blunders and self.same_labels >= self.bar


def summary_from(game: str, fixture: Path) -> tuple[GameSummary, dict[str, float]]:
    """The app's summary of an owner game from one capture, and its engine seconds by tier."""
    settings = Settings(_env_file=None)
    pgn = next((FIXTURES / "pgn" / "user").glob(f"{game}.*")).read_text()
    engine = json.loads(fixture.read_text())
    parsed = parse_pgn(
        pgn, max_chars=settings.limits.max_pgn_chars, max_plies=settings.limits.max_plies
    )
    color = engine["user_color"]
    elo = int(parsed.headers.get("WhiteElo" if color == "white" else "BlackElo", 1200))
    results = [EngineResult.model_validate(r) for r in engine["scan"] + engine["verify"]]
    user = UserInfo(color=color, elo=elo, playstyle=None)
    seconds = {tier: sum(r["time_ms"] for r in engine[tier]) / 1000 for tier in ("scan", "verify")}
    return build_summary(parsed, results, user, settings), seconds


def compare(
    game: str,
    before: GameSummary,
    after: GameSummary,
    seconds: tuple[dict[str, float], dict[str, float]] = ({}, {}),
) -> Quality:
    old = {m.ply: m for m in before.move_list}
    new = {m.ply: m.classification for m in after.move_list}
    same = sum(1 for ply, move in old.items() if new.get(ply) == move.classification)
    lost_moves = [
        m
        for ply, m in sorted(old.items())
        if m.classification in SERIOUS and new.get(ply) not in SERIOUS
    ]
    named = [
        f"{m.move_number}{'.' if m.side == 'white' else '...'} {m.san} ({m.classification})"
        for m in lost_moves
    ]
    floor = V3_RERUN_AGREEMENT.get(game, min(V3_RERUN_AGREEMENT.values()))
    return Quality(
        game=game,
        same_labels=same / len(old) if old else 1.0,
        bar=floor - SLACK,
        lost=named,
        lost_blunders=[
            n for n, m in zip(named, lost_moves, strict=True) if m.classification == "blunder"
        ],
        moments_before=[m.ply for m in before.moments],
        moments_after=[m.ply for m in after.moments],
        scan_s=(seconds[0].get("scan", 0.0), seconds[1].get("scan", 0.0)),
        verify_s=(seconds[0].get("verify", 0.0), seconds[1].get("verify", 0.0)),
    )


def check(game: str, new: Path = ENGINE) -> Quality:
    before, old_seconds = summary_from(game, BASELINE / f"{game}.json")
    after, new_seconds = summary_from(game, new / f"{game}.json")
    return compare(game, before, after, (old_seconds, new_seconds))


def report(quality: Quality) -> str:
    verdict = "ok" if quality.passed else "FAILS"
    lines = [
        f"{quality.game}: {verdict}. Labels unchanged {quality.same_labels:.1%} "
        f"(bar {quality.bar:.1%}). "
        f"Scan {quality.scan_s[0]:.1f}s -> {quality.scan_s[1]:.1f}s, "
        f"verify {quality.verify_s[0]:.1f}s -> {quality.verify_s[1]:.1f}s."
    ]
    if quality.lost:
        lines.append(f"  No longer a mistake or blunder: {', '.join(quality.lost)}")
    if quality.moments_before != quality.moments_after:
        lines.append(
            f"  Critical moments (plies) were {quality.moments_before}, "
            f"now {quality.moments_after}: the owner reviews these."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("games", nargs="*", help="fixture names (default: every capture in --new)")
    parser.add_argument(
        "--new", type=Path, default=ENGINE, help="captures to compare (default: the fixtures)"
    )
    args = parser.parse_args(argv)
    games = args.games or sorted(path.stem for path in args.new.glob("game*.json"))
    results = [check(game, args.new) for game in games]
    for quality in results:
        print(report(quality))
    return 0 if all(q.passed for q in results) else 1


if __name__ == "__main__":
    sys.exit(main())
