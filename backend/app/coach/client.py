"""Claude API access for the coach (SPEC §7.1). Tests use a fake CoachClient, never the API."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Protocol, cast

import anthropic
from anthropic.types import ContentBlock, MessageParam, TextBlockParam, ToolChoiceParam, ToolParam

from app.coach.payload import Task
from app.config import Effort

_PROMPTS = Path(__file__).parent / "prompts"


@cache
def system_prompt(task: Task) -> str:
    """The shared coaching rules plus only this task's instructions (fewer input tokens)."""
    core = (_PROMPTS / "coach_system.md").read_text()
    return f"{core}\n{(_PROMPTS / f'{task}.md').read_text()}"


@cache
def task_instructions(task: Task) -> str:
    """One task's own instructions (its prompt file), without the shared rules."""
    return (_PROMPTS / f"{task}.md").read_text()


def system_blocks(task: Task, *extra: str) -> list[TextBlockParam]:
    """The task's system prompt plus any extra blocks (the game context), each its own cache
    breakpoint (PLAN_V2 §6 Q11): the prompt is shared by every game's calls for this task, the
    game context by every call about this game."""
    return [
        {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
        for text in (system_prompt(task), *extra)
    ]


def history_breakpoint(messages: Sequence[MessageParam]) -> list[MessageParam]:
    """The conversation with a cache breakpoint at the end of the history (the message before the
    newest), so each new message only pays for itself. Returns copies; `messages` is unchanged."""
    copied = [cast(MessageParam, dict(message)) for message in messages]
    if len(copied) < 2:
        return copied
    previous = copied[-2]
    content = previous["content"]
    if isinstance(content, str):
        blocks: list[Any] = [{"type": "text", "text": content}]
    else:
        blocks = [dict(cast(dict[str, Any], block)) for block in content]
    if not blocks or blocks[-1].get("type") in ("thinking", "redacted_thinking"):
        return copied  # thinking blocks can't carry a breakpoint
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    copied[-2] = cast(MessageParam, {**previous, "content": blocks})
    return copied


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


@dataclass(frozen=True)
class CoachRequest:
    model: str
    system: list[TextBlockParam]
    messages: list[MessageParam]
    max_tokens: int
    effort: Effort
    tools: list[ToolParam] = field(default_factory=list)
    tool_choice: ToolChoiceParam | None = None


@dataclass(frozen=True)
class CoachReply:
    text: str
    content: list[ContentBlock]  # all blocks, incl. thinking: replayed unchanged in tool use
    stop_reason: str | None
    usage: Usage
    model: str


class CoachUnavailableError(Exception):
    """The Claude API couldn't be reached or refused the request. `message` is safe to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CoachClient(Protocol):
    async def complete(self, request: CoachRequest) -> CoachReply: ...


class AnthropicCoachClient:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(self, request: CoachRequest) -> CoachReply:
        optional: dict[str, Any] = {"tools": request.tools} if request.tools else {}
        if request.tool_choice is not None:
            optional["tool_choice"] = request.tool_choice
        try:
            # Streaming avoids HTTP timeouts on long responses; the reply is buffered here and
            # validated before anything reaches the player (PLAN Q22).
            async with self._client.messages.stream(
                model=request.model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=request.messages,
                output_config={"effort": request.effort},
                **optional,
            ) as stream:
                message = await stream.get_final_message()
        except anthropic.APIError as error:
            raise CoachUnavailableError(
                "The coach is unavailable right now. Please try again in a minute."
            ) from error
        usage = message.usage
        return CoachReply(
            text="".join(block.text for block in message.content if block.type == "text"),
            content=list(message.content),
            stop_reason=message.stop_reason,
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_input_tokens or 0,
                cache_write_tokens=usage.cache_creation_input_tokens or 0,
            ),
            model=message.model,
        )
