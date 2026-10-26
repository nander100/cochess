"""Server-sent event formatting. Coach endpoints always stream SSE (PLAN Q26)."""

import json
from typing import Any

KEEPALIVE = ": keepalive\n\n"
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def chunks(text: str, size: int = 200) -> list[str]:
    """Split text into pieces of about `size` characters, breaking after whitespace."""
    pieces, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            space = text.rfind(" ", start, end)
            end = space + 1 if space > start else end
        pieces.append(text[start:end])
        start = end
    return pieces
