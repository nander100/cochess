"""The scripted coach the end-to-end tests run against answers each task by name."""

import asyncio
import json

from anthropic.types import MessageParam

from app.coach.client import CoachRequest, system_blocks
from tests.e2e_app import ANSWERS, ScriptedCoach


def test_each_task_gets_its_own_answer() -> None:
    coach = ScriptedCoach()
    for task, answer in ANSWERS.items():
        if task == "walkthrough":
            continue  # answered with the forced tool: below
        payload = json.dumps({"task": task}, separators=(",", ":"))
        message: MessageParam = {"role": "user", "content": f"Answer it.\n\n{payload}"}
        request = CoachRequest(
            model="m", system=system_blocks(task), messages=[message], max_tokens=10, effort="low"
        )
        assert asyncio.run(coach.complete(request)).text == answer


def test_a_walkthrough_is_answered_with_one_step_per_move() -> None:
    payload = json.dumps({"task": "walkthrough", "walkthrough": {"steps": [{}, {}, {}]}})
    message: MessageParam = {"role": "user", "content": f"Walk it.\n\n{payload}"}
    request = CoachRequest(
        model="m", system=system_blocks("walkthrough"), messages=[message], max_tokens=10,
        effort="low",
    )  # fmt: skip

    reply = asyncio.run(ScriptedCoach().complete(request))

    [block] = reply.content
    assert block.type == "tool_use" and block.name == "line_walkthrough"
    assert [step["index"] for step in block.input["steps"]] == [1, 2, 3]
