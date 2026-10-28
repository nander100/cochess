"""The scripted coach the end-to-end tests run against answers each task by name."""

import asyncio
import json

from anthropic.types import MessageParam

from app.coach.client import CoachRequest, system_blocks
from tests.e2e_app import ANSWERS, ScriptedCoach


def test_each_task_gets_its_own_answer() -> None:
    coach = ScriptedCoach()
    for task, answer in ANSWERS.items():
        payload = json.dumps({"task": task}, separators=(",", ":"))
        message: MessageParam = {"role": "user", "content": f"Answer it.\n\n{payload}"}
        request = CoachRequest(
            model="m", system=system_blocks(task), messages=[message], max_tokens=10, effort="low"
        )
        assert asyncio.run(coach.complete(request)).text == answer
