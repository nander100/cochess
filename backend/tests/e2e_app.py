"""The app for frontend end-to-end tests: real backend, scripted coach (no paid API calls).

Run by Playwright (frontend/playwright.config.ts) as
`uvicorn tests.e2e_app:make --factory`. Each answer names its task and no moves, so it passes
move validation and the test can tell which call it got.
"""

import json

import httpx
from anthropic.types import ContentBlock, TextBlock, ToolUseBlock
from fastapi import FastAPI

from app.coach.client import CoachReply, CoachRequest, Usage, system_prompt
from app.coach.payload import Task
from app.config import get_settings
from app.main import create_app

TASKS: tuple[Task, ...] = (
    "synopsis", "chat", "explain", "moment_intro", "moment_feedback", "baseline_report",
    "walkthrough",
)  # fmt: skip
ANSWERS: dict[Task, str] = {
    "synopsis": "### Overall\nE2E synopsis: a fighting game.",
    # A square highlight is valid on any position, so the board tag is always drawn (SPEC_V3 §6).
    # The line link, in its own paragraph, is the position's top engine line (SPEC_V3 §9.4).
    "chat": (
        'E2E chat answer: look at the loose pieces. <board squares="d5:blue"/>\n\n'
        "{{line:here.engine1|Play the engine's idea}}"
    ),
    "explain": "E2E explanation: both sides are developing.",
    "moment_intro": "E2E moment: what would you play here instead?",
    "moment_feedback": "E2E feedback: let's compare your move with the engine's.",
    "baseline_report": "### Overview\nE2E baseline report.",
    "walkthrough": "E2E walkthrough intro: watch the centre.",
}


class ScriptedCoach:
    async def complete(self, request: CoachRequest) -> CoachReply:
        task = _task(request)
        text = ANSWERS[task]
        content: list[ContentBlock] = [TextBlock.model_construct(type="text", text=text)]
        stop = "end_turn"
        if task == "walkthrough":  # the forced line_walkthrough tool: one step per move
            content, text, stop = [_walkthrough_call(request, text)], "", "tool_use"
        return CoachReply(
            text=text,
            content=content,
            stop_reason=stop,
            usage=Usage(input_tokens=1, output_tokens=1, cache_read_tokens=0, cache_write_tokens=0),
            model="e2e-scripted",
        )


def _walkthrough_call(request: CoachRequest, intro: str) -> ContentBlock:
    sent = str(request.messages[0]["content"])
    payload = json.loads(sent.rpartition("\n\n")[2])
    plies = len(payload["walkthrough"]["steps"])
    steps = [{"index": i, "text": f"E2E step {i}: a purposeful move."} for i in range(1, plies + 1)]
    walk = {"intro": intro, "steps": steps, "summary": "E2E takeaway: keep developing."}
    return ToolUseBlock.model_construct(
        type="tool_use", id="toolu_e2e", name="line_walkthrough", input=walk
    )


def _task(request: CoachRequest) -> Task:
    """The task in the latest player message (earlier turns are history), else the one whose
    system prompt this is (the moment tasks share one prompt)."""
    last = next((m for m in reversed(request.messages) if m["role"] == "user"), None)
    sent = str(last["content"]) if last else ""
    for task in TASKS:
        if f'"task":"{task}"' in sent:
            return task
    prompt = request.system[0]["text"]
    return next((t for t in TASKS if system_prompt(t) == prompt), "chat")


# Faked Chess.com and Lichess for the import flows: every player has two games, the first with
# that player as White (the e2e HUNG_KNIGHT game), the second between two other players.
IMPORT_PGN = (
    '[Event "Imported"]\n[White "{white}"]\n[Black "{black}"]\n[Result "0-1"]\n'
    '[Date "2026.10.0{day}"]\n[TimeControl "600"]\n\n{moves}'
)
IMPORT_MOVES = (
    "1. e4 e5 2. Nf3 Nc6 3. Ng5 Qxg5 4. Nc3 Nf6 5. d3 Qg6 6. Be2 Bc5 0-1",
    "1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7 0-1",
)


def _fake_platforms(request: httpx.Request) -> httpx.Response:
    if request.url.host == "lichess.org":
        return _fake_lichess(request)
    return _fake_chesscom(request)


def _fake_lichess(request: httpx.Request) -> httpx.Response:
    """GET /api/games/user/{name}: the same two games as NDJSON, newest first."""
    name = request.url.path.rsplit("/", 1)[-1]
    lines = [
        json.dumps(
            {
                "id": f"e2eLc{i:03}",
                "variant": "standard",
                "lastMoveAt": 1_790_900_000_000 + i,
                "pgn": IMPORT_PGN.format(
                    white=name if i == 0 else "Somebody", black=f"Rival{i}", day=i + 1, moves=moves
                ),
            }
        )
        for i, moves in enumerate(IMPORT_MOVES)
    ]
    return httpx.Response(200, text="\n".join(lines) + "\n")


def _fake_chesscom(request: httpx.Request) -> httpx.Response:
    parts = request.url.path.split("/")  # /pub/player/{name}/games/...
    name = parts[3]
    base = f"https://api.chess.com/pub/player/{name}/games"
    if request.url.path.endswith("/archives"):
        return httpx.Response(200, json={"archives": [f"{base}/2026/10"]})
    games = [
        {
            "url": f"https://www.chess.com/game/live/{900 + i}",
            "pgn": IMPORT_PGN.format(
                white=name if i == 0 else "Somebody", black=f"Rival{i}", day=i + 1, moves=moves
            ),
            "time_class": "rapid",
            "rules": "chess",
            "end_time": 1_790_900_000 + i,
        }
        for i, moves in enumerate(IMPORT_MOVES)
    ]
    return httpx.Response(200, json={"games": games})


def make() -> FastAPI:
    settings = get_settings()
    settings.imports.cooldown_seconds = 0
    # The scripted engine reports full depth at once: searches only need their minimum time.
    engine = settings.engine
    for tier, ms in ((engine.scan, 10), (engine.verify, 20), (engine.deep, 20)):
        tier.min_time_ms = ms
    app = create_app(settings, ScriptedCoach())
    app.state.import_transport = httpx.MockTransport(_fake_platforms)
    return app
