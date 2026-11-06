"""Seed a scratch database with the owner's fixture games, analyzed with their real Stockfish
results, for a demo player (M6 checkpoint: the owner's real dashboard). No coach calls.

Usage (from backend/):
    uv run python -m scripts.seed_owner_games --db /path/to/scratch.db
        [--base-url http://localhost:5175]

Prints a one-time login link for viewing the dashboard in the browser.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth.service import create_invite, create_user
from app.config import Settings
from app.db.models import User
from app.main import create_app
from scripts.print_summary import FIXTURES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--base-url", default="http://localhost:5175")
    args = parser.parse_args()
    if args.db.resolve() == (Path.cwd() / "cochess.db").resolve():
        sys.exit("Use a scratch database, not the app's own.")

    settings = Settings(database_url=f"sqlite:///{args.db}", public_base_url=args.base_url)
    app = create_app(settings)
    with app.state.session_factory() as session:
        user = create_user(session, f"Owner dashboard {datetime.now(UTC):%H%M%S}")
        user.elo, user.time_control = 1350, "rapid"
        session.commit()
        user_id = user.id
        token = create_invite(session, user, datetime.now(UTC), settings.auth)
    client = TestClient(app, base_url="https://testserver")
    assert client.post("/api/auth/redeem", json={"token": token}).status_code == 204

    for path in sorted((FIXTURES / "engine").glob("game*.json")):
        engine = json.loads(path.read_text())
        pgn = next((FIXTURES / "pgn" / "user").glob(f"{path.stem}.*")).read_text()
        game = client.post("/api/games", json={"pgn": pgn, "user_color": engine["user_color"]})
        if game.status_code != 201:
            sys.exit(f"{path.stem}: {game.status_code} {game.text}")
        gid = game.json()["game_id"]
        client.post(f"/api/games/{gid}/engine/scan", json={"results": engine["scan"]})
        verify = client.post(f"/api/games/{gid}/engine/verify", json={"results": engine["verify"]})
        ready = verify.json().get("summary_ready")
        sys.stdout.write(f"{path.stem} as {engine['user_color']}: analyzed={ready}\n")

    with app.state.session_factory() as session:
        owner = session.get(User, user_id)
        assert owner is not None
        link = create_invite(session, owner, datetime.now(UTC), settings.auth)
    sys.stdout.write(f"login link (one use): {settings.public_base_url}/redeem#token={link}\n")


if __name__ == "__main__":
    main()
