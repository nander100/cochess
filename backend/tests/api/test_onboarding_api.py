"""Onboarding endpoints (SPEC_V2 §10, §11): parse, submit, status, and the baseline report."""

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db.models import BaselineReportRow, Game, LlmUsageRow
from app.main import create_app
from tests.analysis_flow import analyze_pgn
from tests.auth_helpers import log_in
from tests.coach_fakes import FakeCoachClient

ME = "nander100"
OPENINGS = ["1. e4 e5 2. Nf3 Nc6", "1. d4 d5 2. c4 e6", "1. c4 e5 2. Nc3 Nf6"]


def pgn(n: int, color: str, result: str, tc: str | None = "600", moves: str | None = None) -> str:
    """A distinct game: player `n` is the opponent, so no two games share a fingerprint."""
    white, black = (ME, f"Opponent {n}") if color == "white" else (f"Opponent {n}", ME)
    headers = [f'[White "{white}"]', f'[Black "{black}"]', f'[Result "{result}"]',
               f'[Date "2026.10.{n + 1:02}"]']  # fmt: skip
    if tc is not None:
        headers.append(f'[TimeControl "{tc}"]')
    return "\n".join(headers) + f"\n\n{moves or OPENINGS[n % 3]} {result}"


def twelve() -> list[str]:
    """3 wins and 3 losses with each color, in rapid."""
    outcomes = [("white", "1-0"), ("white", "0-1"), ("black", "0-1"), ("black", "1-0")] * 3
    return [pgn(i, color, result) for i, (color, result) in enumerate(outcomes)]


def make(*replies: str) -> tuple[TestClient, FakeCoachClient, FastAPI]:
    coach = FakeCoachClient(*replies)
    app = create_app(Settings(_env_file=None, database_url="sqlite://"), coach_client=coach)
    return log_in(app, "Owner", time_control="rapid"), coach, app


def parse(client: TestClient, games: list[str], choices: list[Any] | None = None) -> Any:
    body: dict[str, Any] = {"pgn_text": "\n\n".join(games)}
    if choices is not None:
        body["choices"] = choices
    response = client.post("/api/onboarding/parse", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def submit(client: TestClient, games: list[str], colors: list[str]) -> Any:
    body = {"games": [{"pgn": g, "user_color": c} for g, c in zip(games, colors, strict=True)]}
    response = client.post("/api/onboarding/submit", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def submit_twelve(client: TestClient) -> None:
    games = twelve()
    result = submit(client, games, ["white", "white", "black", "black"] * 3)
    assert all(r["slot"] for r in result["results"])
    for game, row in zip(games, result["results"], strict=True):
        analyze_pgn(client, row["game_id"], game)


def sse_events(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        if lines:
            events.append((lines[0].removeprefix("event: "), json.loads(lines[1][6:])))
    return events


def report_text(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(data["text"] for name, data in events if name == "text")


class TestParse:
    def test_the_paste_becomes_a_table_with_suggested_colors_and_slots(self) -> None:
        client, _, _ = make()

        data = parse(client, [pgn(0, "white", "1-0"), pgn(1, "black", "1-0")])

        assert data["primary_time_control"] == "rapid"
        rows = data["games"]
        assert [(r["white"], r["black"], r["result"], r["date"]) for r in rows] == [
            (ME, "Opponent 0", "1-0", "2026.10.01"),
            ("Opponent 1", ME, "1-0", "2026.10.02"),
        ]
        assert [(r["suggested_color"], r["user_result"], r["slot"]) for r in rows] == [
            ("white", "win", "white_win"),
            ("black", "loss", "black_loss"),
        ]
        assert rows[0]["category"] == "rapid"
        assert rows[0]["pgn"].endswith("1-0")
        assert data["slots"] == [
            {"slot": s, "filled": 0, "of": 3}
            for s in ("white_win", "white_loss", "black_win", "black_loss")
        ]

    def test_games_that_cant_be_used_say_why(self) -> None:
        client, _, _ = make()
        games = [
            pgn(0, "white", "1/2-1/2"),
            pgn(1, "white", "1-0", tc="180+2"),
            pgn(2, "white", "1-0", tc="1/259200"),
            pgn(3, "white", "1-0", tc=None),
            pgn(4, "white", "1-0", moves="1. e4 e4"),
            pgn(5, "white", "1-0"),
            pgn(5, "white", "1-0"),
        ]

        rows = parse(client, games)["games"]

        assert [r["reason"] for r in rows] == [
            "draw",
            "wrong_time_control",
            "wrong_time_control",
            "needs_time_control",
            "invalid_pgn",
            None,
            "duplicate",
        ]
        assert rows[4]["error"]["code"] == "illegal_move"
        assert rows[4]["pgn"] is None

    def test_the_players_choices_settle_color_and_a_missing_time_control(self) -> None:
        client, _, _ = make()
        games = [pgn(0, "white", "1-0", tc=None), pgn(1, "white", "1-0", tc="-")]
        choices = [{"time_control_category": "rapid"}, {"user_color": "black"}]

        rows = parse(client, games, choices)["games"]

        assert [(r["user_color"], r["slot"], r["reason"]) for r in rows] == [
            ("white", "white_win", None),
            ("black", None, "needs_time_control"),
        ]

    def test_a_game_already_uploaded_is_a_duplicate(self) -> None:
        client, _, _ = make()
        game = pgn(0, "white", "1-0")
        uploaded = client.post("/api/games", json={"pgn": game, "user_color": "white"})
        assert uploaded.status_code == 201

        (row,) = parse(client, [game])["games"]

        assert row["reason"] == "duplicate"

    def test_too_many_games(self) -> None:
        client, _, _ = make()

        response = client.post("/api/onboarding/parse", json={"pgn_text": "1. e4 *\n" * 41})

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "too_large"

    def test_the_profile_comes_first(self) -> None:
        app = create_app(Settings(_env_file=None, database_url="sqlite://"), FakeCoachClient())
        client = log_in(app, "New", elo=None, time_control=None)

        response = client.post("/api/onboarding/parse", json={"pgn_text": pgn(0, "white", "1-0")})

        assert response.status_code == 409


class TestSubmit:
    def test_games_that_fill_a_slot_are_stored_as_onboarding_games(self) -> None:
        client, _, app = make()
        games = [pgn(0, "white", "1-0"), pgn(1, "white", "1/2-1/2"), pgn(2, "black", "1-0")]

        data = submit(client, games, ["white", "white", "black"])

        results = data["results"]
        assert [(r["slot"], r["reason"]) for r in results] == [
            ("white_win", None),
            (None, "draw"),
            ("black_loss", None),
        ]
        assert results[1]["game_id"] is None
        with app.state.session_factory() as session:
            stored = list(session.scalars(select(Game)))
        assert {(g.source, g.time_control_category, g.status) for g in stored} == {
            ("onboarding", "rapid", "uploaded")
        }
        assert {g.id for g in stored} == {results[0]["game_id"], results[2]["game_id"]}

    def test_a_full_slot_takes_no_more_games(self) -> None:
        client, _, _ = make()
        submit(client, [pgn(i, "white", "1-0") for i in range(3)], ["white"] * 3)

        data = submit(client, [pgn(3, "white", "1-0")], ["white"])

        assert data["results"][0]["reason"] == "slot_full"
        assert data["slots"][0] == {"slot": "white_win", "filled": 3, "of": 3}

    def test_submitting_the_same_game_again_is_a_duplicate(self) -> None:
        client, _, _ = make()
        submit(client, [pgn(0, "white", "1-0")], ["white"])

        data = submit(client, [pgn(0, "white", "1-0"), pgn(0, "white", "1-0")], ["black", "white"])

        assert [r["reason"] for r in data["results"]] == ["duplicate", "duplicate"]

    def test_the_header_decides_the_time_control_not_the_request(self) -> None:
        client, _, _ = make()
        game = {"pgn": pgn(0, "white", "1-0", tc="60"), "user_color": "white",
                "time_control_category": "rapid"}  # fmt: skip

        data = client.post("/api/onboarding/submit", json={"games": [game]}).json()

        assert data["results"][0]["reason"] == "wrong_time_control"

    def test_onboarding_games_dont_count_toward_the_daily_cap(self) -> None:
        client, _, app = make()
        app.state.settings.limits.max_games_per_day = 1
        submit(client, [pgn(i, "white", "1-0") for i in range(3)], ["white"] * 3)

        body = {"pgn": pgn(9, "white", "1-0"), "user_color": "white"}

        assert client.post("/api/games", json=body).status_code == 201


class TestStatus:
    def test_progress_and_slots(self) -> None:
        client, _, _ = make()
        games = [pgn(0, "white", "1-0"), pgn(1, "black", "1-0")]
        ids = [r["game_id"] for r in submit(client, games, ["white", "black"])["results"]]
        analyze_pgn(client, ids[0], games[0])

        status = client.get("/api/onboarding/status").json()

        assert [(g["id"], g["slot"], g["status"], g["opponent"]) for g in status["games"]] == [
            (ids[0], "white_win", "analyzed", "Opponent 0"),
            (ids[1], "black_loss", "uploaded", "Opponent 1"),
        ]
        assert (status["analyzed"], status["complete"], status["report_ready"]) == (1, False, False)
        assert status["primary_time_control"] == "rapid"
        assert status["report"] is None

    def test_twelve_analyzed_games_are_ready_for_the_report(self) -> None:
        client, _, _ = make()
        submit_twelve(client)

        status = client.get("/api/onboarding/status").json()

        assert (status["analyzed"], status["complete"], status["report_ready"]) == (12, True, True)
        assert all(s["filled"] == 3 for s in status["slots"])

    def test_another_players_onboarding_is_invisible(self) -> None:
        client, _, app = make()
        submit(client, [pgn(0, "white", "1-0")], ["white"])

        other = log_in(app, "Sam", time_control="rapid")

        assert other.get("/api/onboarding/status").json()["games"] == []
        assert other.get("/api/onboarding/report").status_code == 404
        # The same game is not a duplicate for someone else.
        assert submit(other, [pgn(0, "white", "1-0")], ["white"])["results"][0]["slot"]


REPORT = "### Overview\nYou played 1. e4 as White. Your win against Opponent 0 on 2026-10-01."


class TestReport:
    def test_not_before_all_twelve_are_analyzed(self) -> None:
        client, coach, _ = make(REPORT)
        submit(client, [pgn(0, "white", "1-0")], ["white"])

        response = client.post("/api/onboarding/report")

        assert response.status_code == 409
        assert coach.requests == []

    def test_the_report_is_written_validated_and_stored(self) -> None:
        client, coach, app = make(REPORT)
        submit_twelve(client)

        events = sse_events(client.post("/api/onboarding/report").text)

        assert report_text(events) == REPORT
        assert events[-1] == ("done", {"invalid_moves_removed": []})
        (request,) = coach.requests
        assert "the baseline report" in request.system[0]["text"]
        content = request.messages[0]["content"]
        assert isinstance(content, str)
        payload = json.loads(content.split("\n\n", 1)[1])
        assert payload["task"] == "baseline_report"
        assert "color" not in payload["player"]
        assert [g["number"] for g in payload["baseline"]["games"]] == list(range(1, 13))
        stored = client.get("/api/onboarding/report").json()
        assert stored["text"] == REPORT
        assert len(stored["game_ids"]) == 12
        with app.state.session_factory() as session:
            usage = session.scalars(select(LlmUsageRow)).one()
            assert (usage.task, usage.game_id) == ("baseline_report", None)
            assert usage.user_id is not None

    def test_asking_again_shows_the_stored_report_without_a_new_call(self) -> None:
        client, coach, _ = make(REPORT)
        submit_twelve(client)
        client.post("/api/onboarding/report")

        again = sse_events(client.post("/api/onboarding/report").text)

        assert len(coach.requests) == 1
        assert report_text(again) == REPORT
        assert client.get("/api/onboarding/status").json()["report"]["text"] == REPORT

    def test_moves_not_in_the_data_are_regenerated_then_removed(self) -> None:
        client, coach, app = make("Try 1. h4 next time.", "Still 1. h4.")
        submit_twelve(client)

        events = sse_events(client.post("/api/onboarding/report").text)

        assert len(coach.requests) == 2
        note = coach.requests[1].messages[-1]["content"]
        assert isinstance(note, str) and "h4" in note
        assert events[-1] == ("done", {"invalid_moves_removed": ["h4"]})
        with app.state.session_factory() as session:
            row = session.scalars(select(BaselineReportRow)).one()
            assert row.invalid_moves_removed == ["h4"]


@pytest.mark.parametrize("path", ["/api/onboarding/status", "/api/onboarding/report"])
def test_onboarding_needs_a_login(anon_client: TestClient, path: str) -> None:
    assert anon_client.get(path).status_code == 401
