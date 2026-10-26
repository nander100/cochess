"""Claude API access for the coach (SPEC §7.1). Tests use a fake CoachClient, never the API."""

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Protocol

import anthropic
from anthropic.types import ContentBlock, MessageParam, TextBlockParam, ToolParam

from app.config import Effort

_PROMPTS = Path(__file__).parent / "prompts"


@cache
def system_prompt() -> str:
    return (_PROMPTS / "coach_system.md").read_text()


def system_blocks(*extra: str) -> list[TextBlockParam]:
    """The system prompt, marked for prompt caching (it's identical on every call), plus any
    extra blocks. The cache breakpoint goes on the last block so they're cached together."""
    blocks: list[TextBlockParam] = [
        {"type": "text", "text": text} for text in (system_prompt(), *extra)
    ]
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


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
