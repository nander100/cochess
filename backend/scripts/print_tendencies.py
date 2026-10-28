"""Print a player's tendencies with the math behind them (SPEC_V2 §9.2): each game's age and
weight, each theme's per-game counts and weighted sums, then the report the coach gets.

Usage (from backend/): uv run python -m scripts.print_tendencies --user "Alex"
Reads the database in DATABASE_URL (run `python -m app.cli backfill` first for v1 games).
"""

import argparse
import json

from sqlalchemy.orm import sessionmaker

from app.analysis.tendencies import aggregate, theme_sums, weigh
from app.auth.service import find_user
from app.config import Settings
from app.db.session import make_engine
from app.db.tendencies import game_facts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True)
    args = parser.parse_args()
    settings = Settings()
    cfg = settings.tendencies
    with sessionmaker(make_engine(settings.database_url))() as session:
        user = find_user(session, args.user)
        if user is None:
            raise SystemExit(f'no user named "{args.user}"')
        games = game_facts(session, user.id)

    weighted = weigh(games, cfg)
    total = sum(g.weight for g in weighted)
    print(f"Games: {len(weighted)}, half-life {cfg.half_life_games:g} games, weights by severity "
          f"{cfg.severity_weights}\n")  # fmt: skip
    print("age  weight  played      color  accuracy  game")
    for g in weighted:
        accuracy = "-" if g.game.accuracy is None else f"{g.game.accuracy:.1f}"
        print(f"{g.age:>3}  {g.weight:.4f}  {g.game.played_at:%Y-%m-%d}  {g.game.user_color:<5}  "
              f"{accuracy:>8}  {g.game.game_id[:8]}")  # fmt: skip
    print(f"     sum of weights = {total:.4f}\n")

    for sums in theme_sums(weighted, cfg):
        print(f"{sums.theme}")
        print(f"  counts by age:   {sums.counts}")
        print(f"  severity by age: {[round(s, 2) for s in sums.severity]}")
        print(f"  rate  = sum(w*count)/sum(w)    = {sums.weighted_count:.4f} / {total:.4f} "
              f"= {sums.weighted_count / total:.4f}")  # fmt: skip
        print(f"  score = sum(w*severity)/sum(w) = {sums.weighted_severity:.4f} / {total:.4f} "
              f"= {sums.weighted_severity / total:.4f}")  # fmt: skip
    print("\nReport:")
    print(json.dumps(aggregate(games, cfg).model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
