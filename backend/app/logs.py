"""Logs for production (SPEC_V4 §12.3): one JSON object per line for CloudWatch, each with the
request's id; an access line per request without its query string (OAuth codes, unsubscribe
tokens); and a last-chance filter that blanks anything shaped like an email, a key or a token,
so the logs never hold them even if a message slips one in."""

import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import UTC, datetime

from fastapi import Request, Response

request_id: ContextVar[str] = ContextVar("request_id", default="-")
access = logging.getLogger("app.access")

_SECRETS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    (
        re.compile(r"\b(sk-ant-|sk_live_|sk_test_|rk_live_|rk_test_|whsec_)[A-Za-z0-9_-]+"),
        r"\1[redacted]",
    ),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [redacted]"),
    (re.compile(r"(?i)\b(token|code|state|nonce|session|password)=[^&\s\"']+"), r"\1=[redacted]"),
]
_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_QUIET = "/api/health"  # called every few seconds by Docker and the uptime check


def redact(text: str) -> str:
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "request_id": request_id.get(),
        }
        for field in ("method", "path", "status", "ms"):
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info:
            entry["error"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(as_json: bool, level: str = "INFO") -> None:
    """JSON lines on stderr (production) or the plain default (development)."""
    handler = logging.StreamHandler()
    plain = logging.Formatter("%(levelname)s %(name)s: %(message)s")
    handler.setFormatter(JsonFormatter() if as_json else plain)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []  # through the root handler, in the same format
        logging.getLogger(name).propagate = True


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Give the request an id (kept from X-Request-ID when it looks like one), send it back, and
    log one access line: method, path without the query, status, milliseconds."""
    given = request.headers.get("x-request-id", "")
    current = given if _ID.match(given) else uuid.uuid4().hex
    token = request_id.set(current)
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = current
        return response
    finally:
        path = request.url.path
        if not (path == _QUIET and status == 200):
            elapsed = round((time.perf_counter() - started) * 1000)
            fields = {"method": request.method, "path": path, "status": status, "ms": elapsed}
            access.info("%s %s %s", request.method, path, status, extra=fields)
        request_id.reset(token)
