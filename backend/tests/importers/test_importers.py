"""Lichess and Chess.com importers (SPEC_V3 §10) against faked APIs."""

from datetime import date

import httpx
import pytest

from app.config import ImportSettings
from app.importers.base import ImportFailure, ImportQuery
from app.importers.service import fetch_games
from tests.importers.fakes import (
    chesscom_api,
    chesscom_game,
    lichess_game,
    lichess_games,
    recording,
)

SETTINGS = ImportSettings(app_name="CoChess", contact="owner@example.com")


class TestLichess:
    def test_standard_games_come_back_with_their_ids_and_links(self) -> None:
        transport, seen = recording(
            lichess_games(lichess_game(1), lichess_game(2, variant="chess960"), lichess_game(3))
        )

        games = fetch_games("lichess", ImportQuery("me", 20), SETTINGS, transport)

        assert [g.external_id for g in games] == ["lc000001", "lc000003"]
        assert games[0].url == "https://lichess.org/lc000001" and games[0].played_at is not None
        assert seen[0].url.path == "/api/games/user/me"
        assert seen[0].headers["User-Agent"] == "CoChess (owner@example.com)"
        assert seen[0].headers["Accept"] == "application/x-ndjson"

    def test_filters_become_query_parameters(self) -> None:
        transport, seen = recording(lichess_games())

        fetch_games(
            "lichess", ImportQuery("me", 30, "blitz", date(2026, 10, 1)), SETTINGS, transport
        )

        params = seen[0].url.params
        assert (params["max"], params["perfType"]) == ("30", "blitz")
        assert params["since"] == str(1_790_812_800_000)  # 2026-10-01 00:00 UTC in ms


class TestChesscom:
    def test_archives_are_read_newest_first_until_enough_games(self) -> None:
        api = chesscom_api(
            {
                "2026/09": [chesscom_game(1), chesscom_game(2)],
                "2026/10": [chesscom_game(3), chesscom_game(4)],
            }
        )
        transport, seen = recording(api)

        games = fetch_games("chesscom", ImportQuery("Me", 3), SETTINGS, transport)

        assert [g.external_id for g in games] == ["1004", "1003", "1002"]
        assert [r.url.path for r in seen] == [
            "/pub/player/me/games/archives",
            "/pub/player/me/games/2026/10",
            "/pub/player/me/games/2026/09",
        ]
        assert seen[0].headers["User-Agent"] == "CoChess (owner@example.com)"

    def test_variants_other_time_controls_and_older_games_are_left_out(self) -> None:
        october = 1_790_835_960  # 2026-10-01 06:26 UTC
        api = chesscom_api(
            {
                "2026/08": [chesscom_game(1, end_time=1_786_752_000)],  # 2026-08-15
                "2026/10": [
                    chesscom_game(2, end_time=october, rules="chess960"),
                    chesscom_game(3, end_time=october, time_class="blitz"),
                    chesscom_game(4, end_time=october),
                ],
            }
        )
        transport, seen = recording(api)

        games = fetch_games(
            "chesscom", ImportQuery("me", 20, "rapid", date(2026, 10, 1)), SETTINGS, transport
        )

        assert [g.external_id for g in games] == ["1004"]
        assert all("2026/08" not in r.url.path for r in seen)  # older months aren't read

    def test_archive_links_off_the_api_are_not_followed(self) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/archives"):
                return httpx.Response(200, json={"archives": ["https://evil.example/steal"]})
            raise AssertionError(f"followed {request.url}")

        assert (
            fetch_games("chesscom", ImportQuery("me", 5), SETTINGS, httpx.MockTransport(handle))
            == []
        )


@pytest.mark.parametrize("platform", ["lichess", "chesscom"])
@pytest.mark.parametrize(
    ("status", "kind"), [(404, "not_found"), (429, "rate_limited"), (503, "unavailable")]
)
def test_platform_errors_become_clear_failures(platform: str, status: int, kind: str) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status))

    with pytest.raises(ImportFailure) as caught:
        fetch_games(platform, ImportQuery("ghost", 5), SETTINGS, transport)  # type: ignore[arg-type]

    assert caught.value.kind == kind
    if kind == "not_found":
        assert "ghost" in str(caught.value)


@pytest.mark.parametrize("platform", ["lichess", "chesscom"])
def test_a_platform_that_cannot_be_reached_is_unavailable(platform: str) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(ImportFailure) as caught:
        fetch_games(platform, ImportQuery("me", 5), SETTINGS, httpx.MockTransport(fail))  # type: ignore[arg-type]

    assert caught.value.kind == "unavailable"


def test_without_a_contact_the_user_agent_is_the_app_name() -> None:
    assert ImportSettings(app_name="CoChess").user_agent() == "CoChess"
