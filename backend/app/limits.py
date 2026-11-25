"""Rate limits in the database (SPEC_V4 §12.2). Fixed windows: each attempt adds one to its key's
row for the current window with one atomic upsert, committed at once, so a request that fails
afterwards (a bad login link) still counts, and two at the same moment can't both slip through.
Rows of finished windows are cleared as limits are hit."""

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session
from app.config import RateLimits, Settings
from app.db.models import RateLimitRow

MINUTE, DAY = 60, 86_400
KEEP = timedelta(days=2)  # older windows are cleared (the longest limit is a day)
TOO_MANY = "Too many attempts. Please wait {wait} and try again."


def hit(session: Session, key: str, limit: int, window_seconds: int, now: datetime) -> int | None:
    """Count one attempt on `key`. None if it's within `limit` for this window; otherwise the
    seconds until the next window starts."""
    start = int(now.timestamp()) // window_seconds * window_seconds
    window_start = datetime.fromtimestamp(start, UTC)
    insert = postgres_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = (
        insert(RateLimitRow)
        .values(key=key, window_start=window_start, count=1)
        .on_conflict_do_update(
            index_elements=["key", "window_start"], set_={"count": RateLimitRow.count + 1}
        )
        .returning(RateLimitRow.count)
    )
    count = session.execute(statement).scalar_one()
    session.execute(
        delete(RateLimitRow).where(
            RateLimitRow.key == key, RateLimitRow.window_start < window_start
        )
    )
    session.execute(delete(RateLimitRow).where(RateLimitRow.window_start < now - KEEP))
    session.commit()
    if count <= limit:
        return None
    return max(1, math.ceil(start + window_seconds - now.timestamp()))


def client_ip(request: Request, proxy_hops: int) -> str:
    """The client's address. Behind `proxy_hops` trusted proxies that each append to
    X-Forwarded-For, it's the entry that many from the right; entries further left came from the
    client and could be anything."""
    direct = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if proxy_hops <= 0 or not forwarded:
        return direct
    entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
    return entries[-proxy_hops] if len(entries) >= proxy_hops else entries[0]


def check(
    session: Session, key: str, limit: int, window_seconds: int, message: str = TOO_MANY
) -> None:
    """Raise 429 (with Retry-After) when `key` is over `limit` in this window."""
    wait = hit(session, key, limit, window_seconds, datetime.now(UTC))
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=message.format(wait=_words(wait)),
            headers={"Retry-After": str(wait)},
        )


def per_address(name: str, limit: Callable[[RateLimits], int]) -> Callable[..., None]:
    """A route dependency: `limit` attempts per minute from one address."""

    def dependency(
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        settings: Annotated[Settings, Depends(get_app_settings)],
    ) -> None:
        address = client_ip(request, settings.rate_limits.proxy_hops)
        check(session, f"{name}:{address}", limit(settings.rate_limits), MINUTE)

    return dependency


def _words(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} seconds"
    if seconds < 2 * 3600:
        return f"{math.ceil(seconds / 60)} minutes"
    return f"{math.ceil(seconds / 3600)} hours"
