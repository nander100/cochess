"""Facts read from a game's PGN headers: when it was played, and how it ended for the user."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal

from app.analysis.evals import Color

UserResult = Literal["win", "loss", "draw"]

_RESULTS: dict[str, Color | None] = {"1-0": "white", "0-1": "black", "1/2-1/2": None}


def played_at(headers: Mapping[str, str]) -> datetime | None:
    """`UTCDate` + `UTCTime` (Lichess, Chess.com), else `Date`. None if missing or partial
    ("2026.??.??"), so the caller falls back to the upload time (SPEC_V2 §9.2)."""
    for date_key, time_key in (("UTCDate", "UTCTime"), ("Date", None)):
        date = headers.get(date_key, "").strip()
        time = headers.get(time_key, "").strip() if time_key else ""
        parsed = _parse(date, time)
        if parsed is not None:
            return parsed
    return None


def user_result(result: str | None, user_color: Color) -> UserResult | None:
    """win / loss / draw for the user, or None for an unfinished game ("*")."""
    key = (result or "").strip()
    if key not in _RESULTS:
        return None
    winner = _RESULTS[key]
    if winner is None:
        return "draw"
    return "win" if winner == user_color else "loss"


def _parse(date: str, time: str) -> datetime | None:
    try:
        day = datetime.strptime(date, "%Y.%m.%d")
    except ValueError:
        return None
    try:
        clock = datetime.strptime(time, "%H:%M:%S")
    except ValueError:
        clock = datetime.min
    return day.replace(hour=clock.hour, minute=clock.minute, second=clock.second, tzinfo=UTC)


def opening_name(headers: Mapping[str, str]) -> str | None:
    """The `Opening` header, else "ECO B12" from the `ECO` header, else None."""
    if headers.get("Opening"):
        return headers["Opening"]
    return f"ECO {headers['ECO']}" if headers.get("ECO") else None
