"""A scripted CoachClient: never calls the Anthropic API (CLAUDE.md testing rules)."""

from anthropic.types import TextBlock

from app.coach.client import CoachReply, CoachRequest, Usage

FAKE_USAGE = Usage(
    input_tokens=1200, output_tokens=400, cache_read_tokens=900, cache_write_tokens=0
)


class FakeCoachClient:
    """Answers each call with the next scripted reply (text, or an exception to raise)."""

    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[CoachRequest] = []

    async def complete(self, request: CoachRequest) -> CoachReply:
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return CoachReply(
            text=reply,
            content=[TextBlock.model_construct(type="text", text=reply)],
            stop_reason="end_turn",
            usage=FAKE_USAGE,
            model="fake-model",
        )
