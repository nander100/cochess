import json
import logging
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.coach.client import CoachUnavailableError
from app.coach.service import generate_synopsis
from app.coach.validate import REMOVED
from app.config import Settings
from app.db.models import ChatMessageRow, LlmUsageRow
from app.main import create_app
from tests.analysis_flow import analyzed_game
from tests.coach_fakes import FakeCoachClient

VALID = "### Overall\nA classic: 13. Rxd7 Rxd7 and 17. Rd8# finished it."
INVALID = "### Overall\nYou could have played 9. Ka8 or Qh5 instead."


def make(*replies: str | Exception) -> tuple[TestClient, FakeCoachClient, FastAPI]:
    coach = FakeCoachClient(*replies)
    app = create_app(Settings(_env_file=None, database_url="sqlite://"), coach_client=coach)
    return TestClient(app), coach, app


def sse_events(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        if lines:
            name = lines[0].removeprefix("event: ")
            events.append((name, json.loads(lines[1].removeprefix("data: "))))
    return events


async def synopsis_for(coach: FakeCoachClient, app: FastAPI, game_id: str) -> Any:
    return await generate_synopsis(coach, app.state.settings, app.state.session_factory, game_id)


class TestService:
    async def test_a_valid_synopsis_is_stored_with_its_usage(self) -> None:
        client, coach, app = make(VALID)
        game_id = analyzed_game(client)

        result = await synopsis_for(coach, app, game_id)

        assert (result.text, result.invalid_moves_removed) == (VALID, [])
        [request] = coach.requests
        assert request.model == "claude-sonnet-5-5"
        assert (request.max_tokens, request.effort) == (8000, "low")
        assert request.system[-1]["cache_control"] == {"type": "ephemeral"}
        assert str(request.messages[0]["content"]).startswith("Here is the engine")
        with app.state.session_factory() as session:
            usage = session.query(LlmUsageRow).one()
            assert (usage.endpoint, usage.model, usage.input_tokens, usage.cache_read_tokens) == (
                "synopsis",
                "fake-model",
                1200,
                900,
            )

    async def test_invalid_moves_trigger_one_regeneration_with_a_note(self) -> None:
        client, coach, app = make(INVALID, VALID)
        game_id = analyzed_game(client)

        result = await synopsis_for(coach, app, game_id)

        assert result.text == VALID
        retry = coach.requests[1].messages
        assert [m["role"] for m in retry] == ["user", "assistant", "user"]
        assert "Ka8, Qh5" in str(retry[2]["content"])
        with app.state.session_factory() as session:
            assert session.query(LlmUsageRow).count() == 2

    async def test_moves_still_invalid_after_the_retry_are_removed_and_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client, coach, app = make(INVALID, INVALID)
        game_id = analyzed_game(client)

        with caplog.at_level(logging.WARNING):
            result = await synopsis_for(coach, app, game_id)

        assert result.invalid_moves_removed == ["Ka8", "Qh5"]
        assert (
            result.text == f"### Overall\nYou could have played 9. {REMOVED} or {REMOVED} instead."
        )
        assert "coach moves removed" in caplog.text

    async def test_a_stored_synopsis_is_reused_without_calling_claude(self) -> None:
        client, coach, app = make(VALID)
        game_id = analyzed_game(client)
        await synopsis_for(coach, app, game_id)

        again = await synopsis_for(coach, app, game_id)

        assert again.text == VALID
        assert len(coach.requests) == 1
        with app.state.session_factory() as session:
            assert session.query(ChatMessageRow).count() == 1

    async def test_an_overlong_synopsis_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        long_text = VALID + " word" * 400
        client, coach, app = make(long_text)
        game_id = analyzed_game(client)

        with caplog.at_level(logging.WARNING):
            result = await synopsis_for(coach, app, game_id)

        assert result.text == long_text  # kept whole: cutting would break the sections
        assert "synopsis too long" in caplog.text


class TestEndpoint:
    def test_streams_status_then_the_validated_text_then_done(self) -> None:
        client, _, _ = make(VALID)
        game_id = analyzed_game(client)

        response = client.post(f"/api/games/{game_id}/synopsis")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = sse_events(response.text)
        assert events[0] == ("status", {"message": "Coach is writing…"})
        assert "".join(data["text"] for name, data in events if name == "text") == VALID
        assert events[-1] == ("done", {"invalid_moves_removed": []})

    def test_an_api_failure_becomes_an_error_event(self) -> None:
        client, _, _ = make(CoachUnavailableError("The coach is unavailable right now."))
        game_id = analyzed_game(client)

        events = sse_events(client.post(f"/api/games/{game_id}/synopsis").text)

        assert events[-1] == ("error", {"message": "The coach is unavailable right now."})

    def test_needs_a_finished_analysis(self) -> None:
        client, _, _ = make(VALID)
        body = {"pgn": "1. e4 e5 *", "user_color": "white", "elo": 1200}
        game = client.post("/api/games", json=body).json()

        assert client.post(f"/api/games/{game['game_id']}/synopsis").status_code == 409
        assert client.post("/api/games/nope/synopsis").status_code == 404

    def test_without_an_api_key_the_coach_is_unavailable(self, client: TestClient) -> None:
        game_id = analyzed_game(client)  # the default test app has no coach client

        response = client.post(f"/api/games/{game_id}/synopsis")

        assert response.status_code == 503
        assert "ANTHROPIC_API_KEY" in response.json()["detail"]
