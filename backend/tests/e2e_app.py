"""The app for frontend end-to-end tests: real backend, scripted coach (no paid API calls).

Run by Playwright (frontend/playwright.config.ts) as
`uvicorn tests.e2e_app:make --factory`. Each answer names its task and no moves, so it passes
move validation and the test can tell which call it got.
"""

import json

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


def make() -> FastAPI:
    settings = get_settings()
    # The scripted engine reports full depth at once: searches only need their minimum time.
    engine = settings.engine
    for tier, ms in ((engine.scan, 10), (engine.verify, 20), (engine.deep, 20)):
        tier.min_time_ms = ms
    return create_app(settings, ScriptedCoach())
