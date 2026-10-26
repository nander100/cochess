from datetime import UTC, datetime

import pytest

from app.analysis.evals import Color
from app.analysis.game_info import UserResult, played_at, user_result


def test_played_at_prefers_utc_date_and_time() -> None:
    headers = {"Date": "2026.10.01", "UTCDate": "2026.10.02", "UTCTime": "01:30:15"}

    assert played_at(headers) == datetime(2026, 10, 2, 1, 30, 15, tzinfo=UTC)


def test_played_at_falls_back_to_date_at_midnight() -> None:
    assert played_at({"Date": "2026.10.01"}) == datetime(2026, 10, 1, tzinfo=UTC)


def test_played_at_uses_utc_date_without_a_time() -> None:
    assert played_at({"UTCDate": "2026.10.02"}) == datetime(2026, 10, 2, tzinfo=UTC)


@pytest.mark.parametrize("headers", [{}, {"Date": "????.??.??"}, {"Date": "2026.10.??"}])
def test_played_at_is_none_without_a_full_date(headers: dict[str, str]) -> None:
    assert played_at(headers) is None


@pytest.mark.parametrize(
    ("result", "color", "expected"),
    [
        ("1-0", "white", "win"),
        ("1-0", "black", "loss"),
        ("0-1", "black", "win"),
        ("0-1", "white", "loss"),
        ("1/2-1/2", "white", "draw"),
        ("*", "white", None),
        (None, "black", None),
    ],
)
def test_user_result(result: str | None, color: Color, expected: UserResult | None) -> None:
    assert user_result(result, color) == expected
