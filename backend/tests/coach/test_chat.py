import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.coach.client import system_blocks
from app.config import CoachSettings, Settings
from app.db.chat import load_messages, tool_results
from app.db.models import LlmUsageRow, PendingToolCallRow
from app.main import create_app
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import log_in
from tests.coach.test_synopsis import sse_events
from tests.coach_fakes import FakeCoachClient, Reply, ToolCall
from tests.engine_fakes import fake_result

WHAT_IF = {"ply": 9, "candidate_moves_san": ["gxf3"]}  # Opera Game: 5. gxf3 instead of 5. Qxf3
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
# The Opera Game went 1. e4 e5 2. Nf3 d6; the player explores 2...Nc6 3. Bb5 instead.
VARIATION = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]
VARIATION_FEN = "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"


def setup(
    *replies: Reply, coach: CoachSettings | None = None
) -> tuple[TestClient, FakeCoachClient, FastAPI, str]:
    fake = FakeCoachClient(*replies)
    settings = Settings(_env_file=None, database_url="sqlite://", coach=coach or CoachSettings())
    app = create_app(settings, fake)
    client = log_in(app, "Owner")
    return client, fake, app, analyzed_game(client)


def chat(client: TestClient, game_id: str, message: str) -> list[tuple[str, dict[str, Any]]]:
    response = client.post(f"/api/games/{game_id}/chat", json={"message": message})
    assert response.status_code == 200, response.text
    return sse_events(response.text)


def text_of(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(data["text"] for name, data in events if name == "text")


def engine_request(events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    [request] = [data for name, data in events if name == "engine_request"]
    return request


def answer(client: TestClient, game_id: str, request: dict[str, Any]) -> Any:
    results = [
        fake_result(p["fen"], "deep", cp=-40, lines=4, plies=10) for p in request["positions"]
    ]
    body = {"request_id": request["request_id"], "results": results}
    return client.post(f"/api/games/{game_id}/chat/engine_result", json=body)


def history(app: FastAPI, game_id: str) -> list[Any]:
    with app.state.session_factory() as session:
        return load_messages(session, game_id)


def last_user_blocks(fake: FakeCoachClient, call: int) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = fake.requests[call].messages[-1]["content"]  # type: ignore[assignment]
    return content


class TestPlainQuestions:
    def test_answers_with_the_game_in_cached_context(self) -> None:
        client, fake, app, game_id = setup("Your 13. Rxd7 was the key sacrifice.")

        events = chat(client, game_id, "Which move won the game?")

        assert events[0][0] == "status"
        assert text_of(events) == "Your 13. Rxd7 was the key sacrifice."
        [request] = fake.requests
        assert request.model == "claude-haiku-5-5"
        assert [t["name"] for t in request.tools] == ["analyze_position"]
        assert request.tool_choice is None
        context = request.system[1]["text"]
        assert context.startswith("Context for this chat")
        assert '"pgn_to_move":"1. e4 e5' in context
        assert '"move_list"' not in context and "eval_curve" not in context
        assert request.system[-1]["cache_control"] == {"type": "ephemeral"}
        assert [b.get("cache_control") for b in request.system] == [{"type": "ephemeral"}] * 2
        turn = last_user_blocks(fake, 0)[0]["text"]
        payload = json.loads(turn.split("\n\n", 1)[1])
        assert set(payload) == {"task", "user_prompt", "player", "position", "engine_lines"}
        assert (payload["task"], payload["user_prompt"]) == ("chat", "Which move won the game?")
        assert payload["player"] == {"elo": 1350, "color": "white", "rating_band": "intermediate",
                                     "tendencies": []}  # fmt: skip
        # Null fields are left out of what the coach reads: no branch_ply on the game's mainline.
        assert payload["position"] == {"path_san": [], "pgn_to_move": "", "fen": START,
                                       "ply": 0, "on_mainline": True,
                                       "variation_san": []}  # fmt: skip
        assert len(payload["engine_lines"]) == 4  # the start position was verified
        with app.state.session_factory() as session:
            assert session.query(LlmUsageRow).one().endpoint == "chat"

    def test_history_carries_into_the_next_message(self) -> None:
        client, fake, _, game_id = setup("First answer.", "Second answer.")

        chat(client, game_id, "First question?")
        chat(client, game_id, "Second question?")

        assert [m["role"] for m in fake.requests[1].messages] == ["user", "assistant", "user"]

    def test_the_synopsis_is_part_of_the_chat_context(self) -> None:
        client, fake, _, game_id = setup("### Overall\nNice game.", "Sure.")
        client.post(f"/api/games/{game_id}/synopsis")

        chat(client, game_id, "Tell me more.")

        assert "The synopsis you already wrote" in fake.requests[1].system[1]["text"]

    def test_invented_moves_trigger_a_rewrite_without_tools(self) -> None:
        client, fake, _, game_id = setup("Try 5. Ka8 instead.", "The engine prefers 13. Rxd7.")

        events = chat(client, game_id, "What should I have played?")

        assert text_of(events) == "The engine prefers 13. Rxd7."
        assert fake.requests[1].tool_choice == {"type": "none"}


class TestWhatIf:
    def test_round_trip_through_the_browser_engine(self) -> None:
        client, fake, app, game_id = setup(
            ToolCall(WHAT_IF),
            "Taking back with 5. gxf3 is playable, but it weakens your king.",
        )

        request = engine_request(chat(client, game_id, "What if I had played gxf3 on move 5?"))

        assert request["tier"] == "deep"
        assert [p["label"] for p in request["positions"]] == ["position", "after_candidate"]
        with app.state.session_factory() as session:
            assert session.query(PendingToolCallRow).count() == 1

        resumed = answer(client, game_id, request)

        assert resumed.status_code == 200
        # gxf3 is nowhere in the game data; it's allowed because the engine analyzed it.
        assert text_of(sse_events(resumed.text)) == (
            "Taking back with 5. gxf3 is playable, but it weakens your king."
        )
        with app.state.session_factory() as session:
            assert session.query(PendingToolCallRow).count() == 0
            [result] = [json.loads(r) for r in tool_results(session, game_id)]
        assert result["candidate"]["moves_san"] == ["gxf3"]
        assert result["played_in_game"] == "Qxf3"
        # question, tool_use, tool_result
        assert [m["role"] for m in fake.requests[1].messages] == ["user", "assistant", "user"]

    def test_an_illegal_candidate_goes_back_to_the_coach_as_an_error(self) -> None:
        client, fake, _, game_id = setup(
            ToolCall({"ply": 9, "candidate_move_san": "Nxe5"}),
            "Nxe5 isn't possible there: your knight was already gone.",
        )

        events = chat(client, game_id, "What about Nxe5 on move 5?")

        assert not [e for e in events if e[0] == "engine_request"]
        assert events[-1] == ("done", {"invalid_moves_removed": []})
        [tool_result] = last_user_blocks(fake, 1)
        assert tool_result["is_error"] is True
        assert "Nxe5 is not a legal move" in tool_result["content"]

    def test_after_two_tool_calls_the_coach_must_answer(self) -> None:
        client, fake, _, game_id = setup(
            ToolCall({"ply": 999}), ToolCall({"ply": 0}), "I couldn't analyze that position."
        )

        chat(client, game_id, "Analyze something odd.")

        assert [r.tool_choice for r in fake.requests] == [None, None, {"type": "none"}]

    def test_extra_tool_calls_in_one_turn_are_answered_with_errors(self) -> None:
        client, fake, _, game_id = setup(
            ToolCall({"ply": 9}, extra_inputs=[{"ply": 11}]), "Here is what the engine shows."
        )

        answer(client, game_id, engine_request(chat(client, game_id, "Compare moves 5 and 6.")))

        results = last_user_blocks(fake, 1)
        assert [r["tool_use_id"] for r in results] == ["toolu_1", "toolu_1_1"]
        assert results[1]["is_error"] is True

    def test_a_new_message_cancels_a_pending_analysis(self) -> None:
        client, _, app, game_id = setup(ToolCall(WHAT_IF), "OK, a new topic.")

        request = engine_request(chat(client, game_id, "What if gxf3?"))
        chat(client, game_id, "Never mind. What about the opening?")

        turns = history(app, game_id)
        assert [m["role"] for m in turns] == ["user", "assistant", "user", "assistant"]
        cancelled, new_question = turns[2]["content"]
        assert cancelled["is_error"] is True and "cancelled" in cancelled["content"]
        assert new_question["type"] == "text"
        assert answer(client, game_id, request).status_code == 404


class TestValidation:
    def test_results_must_match_the_requested_positions(self) -> None:
        client, _, _, game_id = setup(ToolCall(WHAT_IF))
        request = engine_request(chat(client, game_id, "What if gxf3?"))

        wrong = {**request, "positions": request["positions"][:1]}

        assert answer(client, game_id, wrong).status_code == 422

    def test_unknown_request_ids_are_not_found(self) -> None:
        client, _, _, game_id = setup()

        response = client.post(
            f"/api/games/{game_id}/chat/engine_result", json={"request_id": "nope", "results": []}
        )

        assert response.status_code == 404

    def test_message_length_and_chat_limit(self) -> None:
        limits = CoachSettings(chat_max_message_chars=10, chat_max_messages=1)
        client, _, _, game_id = setup("One answer.", coach=limits)
        url = f"/api/games/{game_id}/chat"

        assert client.post(url, json={"message": "x" * 11}).status_code == 422
        assert client.post(url, json={"message": "   "}).status_code == 422
        chat(client, game_id, "Hi coach")
        limited = client.post(url, json={"message": "Again"})

        assert limited.status_code == 429
        assert "limit of 1 questions" in limited.json()["detail"]


def ask(
    client: TestClient,
    game_id: str,
    message: str,
    path: list[str],
    engine_result: dict[str, Any] | None = None,
) -> Any:
    body: dict[str, Any] = {"message": message, "path_uci": path}
    if engine_result is not None:
        body["engine_result"] = engine_result
    return client.post(f"/api/games/{game_id}/chat", json=body)


def payload_of(fake: FakeCoachClient, call: int) -> Any:
    # The JSON is the turn's last paragraph (Explain's instructions come before it).
    return json.loads(last_user_blocks(fake, call)[0]["text"].rsplit("\n\n", 1)[1])


class TestPositions:
    def test_a_question_from_a_variation_carries_the_position_and_its_engine_lines(self) -> None:
        client, fake, _, game_id = setup("In your line, 3...a6 asks the bishop a question.")
        result = fake_result(VARIATION_FEN, "verify", cp=25, lines=4, plies=12)

        response = ask(client, game_id, "Is Bb5 good here?", VARIATION, result)

        assert response.status_code == 200, response.text
        payload = payload_of(fake, 0)
        assert payload["position"] == {
            "path_san": ["e4", "e5", "Nf3", "Nc6", "Bb5"],
            "pgn_to_move": "1. e4 e5 2. Nf3 Nc6 3. Bb5",
            "fen": VARIATION_FEN,
            "ply": 5,
            "on_mainline": False,
            "branch_ply": 4,
            "variation_san": ["Nc6", "Bb5"],
        }
        lines = payload["engine_lines"]
        assert len(lines) == 4 and lines[0]["eval"] == "+0.2"
        assert {len(line["moves_san"]) for line in lines} == {10}  # trimmed to the verify tier
        detail = client.get(f"/api/games/{game_id}").json()
        assert detail["chat"][0] == {
            "role": "player",
            "text": "Is Bb5 good here?",
            "where": "after 3. Bb5, in your line",
        }
        assert any(r["fen"] == VARIATION_FEN for r in detail["engine_results"])

    def test_the_stored_result_is_reused_for_the_next_question(self) -> None:
        client, fake, _, game_id = setup("First.", "Second.")
        result = fake_result(VARIATION_FEN, "verify", cp=25, lines=4, plies=10)
        ask(client, game_id, "Is Bb5 good?", VARIATION, result)

        response = ask(client, game_id, "And now?", VARIATION)

        assert response.status_code == 200
        assert payload_of(fake, 1)["engine_lines"] == payload_of(fake, 0)["engine_lines"]

    def test_a_position_without_analysis_is_refused_before_the_coach_runs(self) -> None:
        client, fake, _, game_id = setup("unused")

        response = ask(client, game_id, "Is Bb5 good?", VARIATION)

        assert response.status_code == 409
        assert "hasn't analyzed this position" in response.json()["detail"]
        assert fake.requests == []

    def test_an_engine_result_for_another_position_is_refused(self) -> None:
        client, fake, _, game_id = setup("unused")
        wrong = fake_result(START, "verify", lines=4, plies=10)

        response = ask(client, game_id, "Is Bb5 good?", VARIATION, wrong)

        assert response.status_code == 422
        assert "different position" in response.json()["detail"]
        assert fake.requests == []

    def test_an_illegal_path_is_refused(self) -> None:
        client, fake, _, game_id = setup("unused")

        response = ask(client, game_id, "Hm?", ["e2e4", "e2e4"])

        assert response.status_code == 422
        assert "isn't legal" in response.json()["detail"]
        assert fake.requests == []

    def test_a_tool_call_without_a_ply_analyzes_the_board_position(self) -> None:
        client, _, _, game_id = setup(
            ToolCall({"candidate_moves_san": ["a6"]}), "After 3...a6 the bishop has to decide."
        )
        result = fake_result(VARIATION_FEN, "verify", lines=4, plies=10)

        events = sse_events(ask(client, game_id, "What about a6?", VARIATION, result).text)
        request = engine_request(events)
        resumed = answer(client, game_id, request)

        assert request["positions"][0]["fen"] == VARIATION_FEN
        assert text_of(sse_events(resumed.text)) == "After 3...a6 the bishop has to decide."

    def test_the_player_is_their_profile_today(self) -> None:
        client, fake, _, game_id = setup("Sure.")
        client.patch("/api/me", json={"elo": 1750, "playstyle": "positional"})

        ask(client, game_id, "Hi", [])

        assert payload_of(fake, 0)["player"] == {
            "elo": 1750,
            "color": "white",
            "rating_band": "intermediate",
            "playstyle": "positional",
            "tendencies": [],
        }

    def test_the_conversation_so_far_is_cached(self) -> None:
        client, fake, _, game_id = setup("First answer.", "Second answer.")
        ask(client, game_id, "First?", [])

        ask(client, game_id, "Second?", [])

        messages = fake.requests[1].messages
        assert messages[1]["content"][-1]["cache_control"] == {"type": "ephemeral"}  # type: ignore[index]
        assert "cache_control" not in str(messages[2])

    def test_moves_shown_in_an_earlier_turn_stay_valid(self) -> None:
        result = fake_result(VARIATION_FEN, "verify", lines=4, plies=10)
        first_line_move = "a6"  # fake_result's first legal move in UCI order from VARIATION_FEN
        client, fake, _, game_id = setup("Look at that.", f"Like I said, 3...{first_line_move}.")
        ask(client, game_id, "Is Bb5 good?", VARIATION, result)

        events = sse_events(ask(client, game_id, "Remind me?", []).text)

        assert first_line_move in text_of(events)
        assert len(fake.requests) == 2  # no rewrite was needed


class TestExplain:
    def explain(self, client: TestClient, game_id: str, path: list[str]) -> Any:
        return client.post(f"/api/games/{game_id}/explain", json={"path_uci": path})

    def test_explains_the_board_position_without_tools_and_joins_the_chat(self) -> None:
        client, fake, app, game_id = setup("### What has happened\nA calm start.")

        response = self.explain(client, game_id, [])

        assert response.status_code == 200, response.text
        assert text_of(sse_events(response.text)) == "### What has happened\nA calm start."
        [request] = fake.requests
        # Explain shares the chat's system prompt (and so its cached prefix); its own
        # instructions are in its user turn.
        assert request.system == system_blocks("chat", request.system[1]["text"])
        assert last_user_blocks(fake, 0)[0]["text"].startswith("# Your task now: Explain")
        assert request.tool_choice == {"type": "none"}
        payload = payload_of(fake, 0)
        assert (payload["task"], payload.get("user_prompt")) == ("explain", None)
        assert payload["position"]["ply"] == 0 and len(payload["engine_lines"]) == 4
        assert client.get(f"/api/games/{game_id}").json()["chat"] == [
            {"role": "player", "text": "Explain this position", "where": "the start"},
            {"role": "coach", "text": "### What has happened\nA calm start.", "where": None},
        ]
        with app.state.session_factory() as session:
            assert session.query(LlmUsageRow).one().task == "explain"

    def test_moves_shown_by_explain_stay_valid_in_later_answers(self) -> None:
        result = fake_result(VARIATION_FEN, "verify", lines=4, plies=10)
        client, fake, _, game_id = setup("Here it is.", "As I said, 3...a6 is the line.")
        body = {"path_uci": VARIATION, "engine_result": result}
        assert client.post(f"/api/games/{game_id}/explain", json=body).status_code == 200

        events = sse_events(ask(client, game_id, "Remind me?", []).text)

        assert "3...a6" in text_of(events)  # a6 was only in the Explain payload's engine lines
        assert len(fake.requests) == 2  # no rewrite

    def test_needs_an_analyzed_position(self) -> None:
        client, fake, _, game_id = setup("unused")

        assert self.explain(client, game_id, VARIATION).status_code == 409
        assert fake.requests == []

    def test_shares_the_question_limit(self) -> None:
        client, _, _, game_id = setup("One.", coach=CoachSettings(chat_max_messages=1))
        self.explain(client, game_id, [])

        response = self.explain(client, game_id, [])

        assert response.status_code == 429
