"""A scripted CoachClient: never calls the Anthropic API (CLAUDE.md testing rules)."""

from dataclasses import dataclass, field
from typing import Any

from anthropic.types import ContentBlock, TextBlock, ToolUseBlock

from app.coach.client import CoachReply, CoachRequest, Usage

FAKE_USAGE = Usage(
    input_tokens=1200, output_tokens=400, cache_read_tokens=900, cache_write_tokens=0
)


@dataclass(frozen=True)
class ToolCall:
    """A scripted reply that calls analyze_position."""

    input: dict[str, Any]
    id: str = "toolu_1"
    extra_inputs: list[dict[str, Any]] = field(default_factory=list)  # more calls, same turn


Reply = str | ToolCall | Exception


class FakeCoachClient:
    """Answers each call with the next scripted reply: text, a tool call, or an exception."""

    def __init__(self, *replies: Reply) -> None:
        self.replies = list(replies)
        self.requests: list[CoachRequest] = []

    async def complete(self, request: CoachRequest) -> CoachReply:
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, ToolCall):
            calls = [reply.input, *reply.extra_inputs]
            content: list[ContentBlock] = [
                ToolUseBlock.model_construct(
                    type="tool_use", id=f"{reply.id}_{i}" if i else reply.id,
                    name="analyze_position", input=call,
                )
                for i, call in enumerate(calls)
            ]  # fmt: skip
            return CoachReply("", content, "tool_use", FAKE_USAGE, "fake-model")
        return CoachReply(
            text=reply,
            content=[TextBlock.model_construct(type="text", text=reply)],
            stop_reason="end_turn",
            usage=FAKE_USAGE,
            model="fake-model",
        )
