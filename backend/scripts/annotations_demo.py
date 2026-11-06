"""Real coach replies on an owner fixture game: board tags (M3, SPEC_V3 §6), move tags and line
links at a detail level (M5, §9).

Usage (from backend/):
    uv run python -m scripts.annotations_demo game1w --db /path/to/scratch.db
        [--level plain|standard|technical] [--base-url http://localhost:5175]

Seeds a scratch database (never the app's own) with the game and its real Stockfish results, then
asks the real coach (ANTHROPIC_API_KEY from .env) through the real endpoints: a chat question at
two critical positions, and a critical moment's intro and a question (unsolved, so the leak check
is on). Prints each reply as the player sees it, its board tags, and the annotation log, then a
login link for viewing the same game in the browser.
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.auth.service import create_invite, create_user
from app.config import Settings
from app.db.models import AnnotationLogRow, LlmUsageRow, User
from app.main import create_app
from scripts.print_summary import FIXTURES

QUESTION = "What should I be paying attention to in this position? Show me on the board."
MOMENT_QUESTION = "Which of my pieces should I be worried about here?"


_PLACEHOLDER = re.compile(r"\[([^\]]*)\]\(cc:(board|move|line)/(\d+)\)")


def shown(text: str, moves: list[dict[str, Any]], level: str) -> str:
    """The reply as the app shows it at `level`: moves as words or notation, line links as
    «link text ▶ reference», board tags as [board]."""

    def one(match: re.Match[str]) -> str:
        label, kind, index = match[1], match[2], int(match[3])
        if kind == "board":
            return "[board]"
        if kind == "line":
            return f"«{label} ▶»"
        move = next(m for m in moves if m["index"] == index)
        if level != "technical":
            return str(move["words"])
        number = move["move_number"]
        dots = "." if move["white"] else "..."
        return f"{number}{dots}{move['san']}" if number is not None else str(move["san"])

    return _PLACEHOLDER.sub(one, text)


def events(body: str) -> tuple[str, list[dict[str, Any]]]:
    """The reply text and its annotation events from an SSE body."""
    text, annotations = "", []
    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        if len(lines) < 2:
            continue
        name, data = lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))
        if name == "text":
            text += data["text"]
        elif name in ("annotation", "move", "line_link"):
            annotations.append({"event": name, **data})
        elif name == "error":
            sys.exit(f"coach error: {data['message']}")
    return text, annotations


def show(title: str, response: Any, level: str) -> None:
    if response.status_code != 200:
        sys.exit(f"{title}: {response.status_code} {response.text}")
    text, tokens = events(response.text)
    moves = [t for t in tokens if t["event"] == "move"]
    links = [t for t in tokens if t["event"] == "line_link"]
    annotations = [t for t in tokens if t["event"] == "annotation"]
    sys.stdout.write(f"----- {title}\n\n{shown(text, moves, level)}\n\n")
    for link in links:
        moves_uci = " ".join(link["moves_uci"])
        sys.stdout.write(f"  line link «{link['label']}»: {link['ref']} = {moves_uci}\n")
    for a in annotations:
        arrows = ", ".join(f"{x['orig']}{x['dest']}:{x['color']}" for x in a["arrows"])
        squares = ", ".join(f"{x['square']}:{x['color']}" for x in a["squares"])
        sys.stdout.write(f"  tag {a['tag_index']}: arrows [{arrows}] squares [{squares}]\n")
    sys.stdout.write("\n" if annotations or links else "  (no board tags or line links)\n\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("game")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--base-url", default="http://localhost:5175")
    parser.add_argument("--level", choices=["plain", "standard", "technical"])
    args = parser.parse_args()
    if args.db.resolve() == (Path.cwd() / "cochess.db").resolve():
        sys.exit("Use a scratch database, not the app's own.")

    settings = Settings(database_url=f"sqlite:///{args.db}", public_base_url=args.base_url)
    if not settings.anthropic_api_key:
        sys.exit("Set ANTHROPIC_API_KEY in backend/.env first.")
    app = create_app(settings)
    engine = json.loads((FIXTURES / "engine" / f"{args.game}.json").read_text())
    pgn = next((FIXTURES / "pgn" / "user").glob(f"{args.game}.*")).read_text()
    color = engine["user_color"]

    with app.state.session_factory() as session:
        user = create_user(session, f"Owner demo {datetime.now(UTC):%H%M%S}")
        user.elo, user.time_control = 1350, "rapid"
        session.commit()
        user_id = user.id
        token = create_invite(session, user, datetime.now(UTC), settings.auth)
    client = TestClient(app, base_url="https://testserver")
    assert client.post("/api/auth/redeem", json={"token": token}).status_code == 204
    if args.level:
        client.patch("/api/settings", json={"coach_detail_level": args.level})
    level = client.get("/api/settings").json()["effective_detail_level"]

    game = client.post("/api/games", json={"pgn": pgn, "user_color": color}).json()
    gid = game["game_id"]
    scan = client.post(f"/api/games/{gid}/engine/scan", json={"results": engine["scan"]})
    verify = client.post(f"/api/games/{gid}/engine/verify", json={"results": engine["verify"]})
    if not verify.json().get("summary_ready"):
        sys.exit(f"analysis didn't finish: {scan.text} {verify.text}")
    detail = client.get(f"/api/games/{gid}").json()
    moments = detail["moments"]
    paths = [[m["uci"] for m in detail["moves"][: moment["ply"] - 1]] for moment in moments]

    sys.stdout.write(
        f"===== {args.game} as {color}: {len(moments)} critical moments, detail level {level}\n\n"
    )
    for moment, path in list(zip(moments, paths, strict=True))[1:3]:
        dots = "." if moment["side"] == "white" else "..."
        title = f"chat, before {moment['move_number']}{dots}{moment['san']} ({moment['label']})"
        body = {"message": QUESTION, "path_uci": path}
        show(title, client.post(f"/api/games/{gid}/chat", json=body), level)

    first = moments[0]["index"]
    show("moment 1 intro (unsolved)", client.post(f"/api/games/{gid}/moments/{first}/start"), level)
    question = {"message": MOMENT_QUESTION}
    show(
        "moment 1 question",
        client.post(f"/api/games/{gid}/moments/{first}/ask", json=question),
        level,
    )

    with app.state.session_factory() as session:
        rows = session.query(AnnotationLogRow).filter_by(user_id=user_id).all()
        sys.stdout.write(f"----- annotation_log ({len(rows)} rows)\n")
        for row in rows:
            sys.stdout.write(
                f"  {row.task} moment={row.moment_index} reason={row.reason} "
                f"shape={row.shape} tag={row.tag}\n"
            )
        calls = session.query(LlmUsageRow).filter_by(game_id=gid).count()
        owner = session.get(User, user_id)
        assert owner is not None
        link = create_invite(session, owner, datetime.now(UTC), settings.auth)
    sys.stdout.write(f"\nClaude calls: {calls}\ngame: /games/{gid}\n")
    sys.stdout.write(f"login link (one use): {settings.public_base_url}/redeem#token={link}\n")


if __name__ == "__main__":
    main()
