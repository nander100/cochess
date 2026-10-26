"""AnthropicCoachClient against a stubbed SDK: checks the request shape, never calls the API."""

from typing import Any

import anthropic
import httpx
import pytest
from anthropic.types import Message, TextBlock, ThinkingBlock, Usage

from app.coach.client import (
    AnthropicCoachClient,
    CoachRequest,
    CoachUnavailableError,
    system_blocks,
)


class StubStream:
    def __init__(self, message: Message) -> None:
        self.message = message

    async def __aenter__(self) -> "StubStream":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get_final_message(self) -> Message:
        return self.message


def final_message() -> Message:
    return Message.model_construct(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-opus-5-5",
        content=[
            ThinkingBlock.model_construct(type="thinking", thinking="", signature="sig"),
            TextBlock.model_construct(type="text", text="### Overall\n"),
            TextBlock.model_construct(type="text", text="Well played."),
        ],
        stop_reason="end_turn",
        usage=Usage.model_construct(
            input_tokens=50,
            output_tokens=300,
            cache_read_input_tokens=1100,
            cache_creation_input_tokens=None,
        ),
    )


REQUEST = CoachRequest(
    model="claude-opus-5-5",
    system=system_blocks("synopsis"),
    messages=[{"role": "user", "content": "payload"}],
    max_tokens=8000,
    effort="medium",
)


async def test_sends_effort_and_cached_system_and_joins_the_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AnthropicCoachClient(api_key="test-key")
    calls: list[dict[str, Any]] = []

    def stream(**kwargs: Any) -> StubStream:
        calls.append(kwargs)
        return StubStream(final_message())

    monkeypatch.setattr(client._client.messages, "stream", stream)

    reply = await client.complete(REQUEST)

    [call] = calls
    assert call["output_config"] == {"effort": "medium"}
    assert call["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert (call["model"], call["max_tokens"]) == ("claude-opus-5-5", 8000)
    assert "tools" not in call
    assert reply.text == "### Overall\nWell played."
    assert [block.type for block in reply.content] == ["thinking", "text", "text"]
    assert (reply.usage.cache_read_tokens, reply.usage.cache_write_tokens) == (1100, 0)


async def test_api_errors_become_a_friendly_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AnthropicCoachClient(api_key="test-key")
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def stream(**kwargs: Any) -> StubStream:
        raise anthropic.APIConnectionError(request=request)

    monkeypatch.setattr(client._client.messages, "stream", stream)

    with pytest.raises(CoachUnavailableError, match="unavailable right now"):
        await client.complete(REQUEST)
