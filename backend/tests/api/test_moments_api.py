"""Critical-moment routes end to end with a scripted coach (SPEC_V2 §8): what the coach is given
at each step (never the best move before solve/reveal), grading, saved progress, and the leak
check. The Opera Game with one blunder: 5. Qxf3 at -3.0 (ply 9)."""

import json
from typing import Any

import chess
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analysis.engine import EngineResult
from app.config import Settings
from app.db.engine_results import save_position_result
from app.db.models import MomentProgressRow
from app.main import create_app
from tests.auth_helpers import log_in
from tests.coach.test_synopsis import sse_events
from tests.coach_fakes import FakeCoachClient, Reply
from tests.engine_fakes import fake_result, legal_line
from tests.pgn_fixtures import read_pgn

MOMENT_FEN = "rn1qkbnr/ppp2ppp/3p4/4P3/4P3/5b2/PPP2PPP/RNBQKB1R w KQkq - 0 5"
INTRO = "You played 5. Qxf3 and went from equal to -3.0. What would you play instead, and why?"
FEEDBACK = "After 5. a3 the engine shows you end up worse. Look again at what your queen does."
SOLVED = "Yes! 5. gxf3 keeps the material balance."


def deep(fen: str, *lines: tuple[str, int]) -> dict[str, Any]:
    built = []
    for rank, (first, cp) in enumerate(lines, start=1):
        board = chess.Board(fen)
        board.push_uci(first)
        moves = [first, *legal_line(board.fen(), 5)]
        built.append({"rank": rank, "eval_cp": cp, "mate": None, "moves_uci": moves})
    return {"ply": None, "fen": fen, "tier": "deep", "depth": 24, "time_ms": 3000, "lines": built}


# The engine's view of the moment: 5. gxf3 holds the balance; the game's 5. Qxf3 loses.
BEFORE = deep(MOMENT_FEN, ("g2f3", 0), ("d1f3", -300))


def after(uci: str, cp: int) -> dict[str, Any]:
    board = chess.Board(MOMENT_FEN)
    board.push_uci(uci)
    return fake_result(board.fen(), "deep", cp=cp, plies=6, depth=24, time_ms=3000)


def setup(*replies: Reply) -> tuple[TestClient, FakeCoachClient, FastAPI, str]:
    fake = FakeCoachClient(*replies)
    app = create_app(Settings(_env_file=None, database_url="sqlite://"), fake)
    client = log_in(app, "Owner")
    assert client.patch("/api/me", json={"elo": 1200}).status_code == 200
    game = client.post(
        "/api/games", json={"pgn": read_pgn("opera_game.pgn"), "user_color": "white"}
    ).json()
    after_blunder = game["positions"][9]["fen_before"]  # the position after 5. Qxf3
    fens = [p["fen_before"] for p in game["positions"]]

    def results(tier: str, wanted: list[str]) -> list[dict[str, Any]]:
        lines, plies = (1, 1) if tier == "scan" else (4, 10)  # what each tier allows
        return [
            fake_result(f, tier, cp=-300 if f == after_blunder else 0, lines=lines, plies=plies)
            for f in wanted
        ]

    gid: str = game["game_id"]
    scan = client.post(f"/api/games/{gid}/engine/scan", json={"results": results("scan", fens)})
    verify = client.post(
        f"/api/games/{gid}/engine/verify",
        json={"results": results("verify", scan.json()["verify_fens"])},
    )
    assert verify.json()["summary_ready"] is True
    return client, fake, app, gid


def store_before(app: FastAPI, gid: str) -> None:
    """The deep search of the moment's position, as if the board had sent it already."""
    with app.state.session_factory() as session:
        save_position_result(session, gid, EngineResult.model_validate(BEFORE))
        session.commit()


def post(client: TestClient, path: str, body: dict[str, Any] | None = None) -> Any:
    response = client.post(path, json=body or {})
    assert response.status_code == 200, response.text
    return sse_events(response.text)


def moment_event(events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    [meta] = [data for name, data in events if name == "moment"]
    return meta


def text_of(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(data["text"] for name, data in events if name == "text")


def payload(fake: FakeCoachClient, call: int = -1) -> dict[str, Any]:
    content = fake.requests[call].messages[0]["content"]
    assert isinstance(content, str)
    data: dict[str, Any] = json.loads(content.rpartition("\n\n")[2])
    return data


def progress(app: FastAPI) -> MomentProgressRow:
    with app.state.session_factory() as session:
        row: MomentProgressRow = session.query(MomentProgressRow).one()
        return row


def attempt(client: TestClient, gid: str, uci: str, cp: int, **extra: Any) -> Any:
    body = {"move_uci": uci, "engine_before": BEFORE, "engine_after": after(uci, cp), **extra}
    return post(client, f"/api/games/{gid}/moments/1/attempt", body)


class TestStart:
    def test_the_intro_withholds_the_answer(self) -> None:
        client, fake, _, gid = setup(INTRO)

        events = post(client, f"/api/games/{gid}/moments/1/start")

        assert text_of(events) == INTRO
        sent = payload(fake)
        assert sent["task"] == "moment_intro"
        moment = sent["moment"]
        assert (moment["state"], moment["reveal"], moment["game_move"]["san"]) == (
            "intro",
            False,
            "5. Qxf3",
        )
        assert "best" not in moment and "engine_lines" not in sent
        # The context is the game up to the moment: it ends with 4...Bxf3.
        context = json.loads(fake.requests[0].system[1]["text"].rpartition("\n\n")[2])
        assert context["pgn_to_move"].split()[-1].startswith("Bxf3")

    def test_returning_shows_the_stored_intro_without_a_new_call(self) -> None:
        client, fake, _, gid = setup(INTRO)
        post(client, f"/api/games/{gid}/moments/1/start")

        events = post(client, f"/api/games/{gid}/moments/1/start")

        assert text_of(events) == INTRO and len(fake.requests) == 1

    def test_a_moment_that_doesnt_exist_is_not_found(self) -> None:
        client, _, _, gid = setup()

        assert client.post(f"/api/games/{gid}/moments/9/start").status_code == 404


class TestLeaks:
    def test_a_leaked_answer_is_regenerated(self) -> None:
        client, fake, app, gid = setup("Try 5. gxf3 here!", INTRO)
        store_before(app, gid)

        events = post(client, f"/api/games/{gid}/moments/1/start")

        assert text_of(events) == INTRO
        assert len(fake.requests) == 2
        note = fake.requests[1].messages[-1]["content"]
        assert isinstance(note, str) and "gxf3" not in note  # the retry doesn't name it either
        assert progress(app).leaks == 0

    def test_a_leak_that_survives_the_retry_is_removed_and_counted(self) -> None:
        client, _, app, gid = setup("Play gxf3.", "Really, 5. gxf3 is it.")
        store_before(app, gid)

        events = post(client, f"/api/games/{gid}/moments/1/start")

        assert "gxf3" not in text_of(events)
        assert progress(app).leaks == 1

    def test_the_same_move_for_another_turn_is_not_a_leak(self) -> None:
        client, fake, app, gid = setup("Remember 2. Nf3 from earlier.")
        store_before(app, gid)

        events = post(client, f"/api/games/{gid}/moments/1/start")

        assert "Nf3" in text_of(events) and len(fake.requests) == 1


class TestAttempts:
    def test_a_failed_attempt_gets_one_hint_and_no_answer(self) -> None:
        client, fake, app, gid = setup(INTRO, FEEDBACK)
        post(client, f"/api/games/{gid}/moments/1/start")

        events = attempt(client, gid, "a2a3", -300, reasoning="Kick the bishop later")

        assert moment_event(events) == {"grade": "blunder", "state": "attempt"}
        sent = payload(fake)
        moment = sent["moment"]
        assert moment["candidate"]["san"] == "5. a3"
        assert moment["earlier_attempts"] == [
            {"san": "a3", "grade": "blunder", "reasoning": "Kick the bishop later"}
        ]
        assert [h["level"] for h in moment["hints_allowed"]] == [1]
        assert moment["reveal"] is False and "best" not in moment
        assert "gxf3" not in json.dumps(sent)
        assert progress(app).state == "attempt"

    def test_the_last_failed_attempt_reveals_the_answer(self) -> None:
        client, fake, _, gid = setup(INTRO, FEEDBACK, "The move was 5. gxf3.")
        post(client, f"/api/games/{gid}/moments/1/start")
        attempt(client, gid, "a2a3", -300)

        events = attempt(client, gid, "h2h3", -300)

        assert moment_event(events) == {"grade": "blunder", "state": "revealed"}
        moment = payload(fake)["moment"]
        assert moment["reveal"] is True and moment["best"]["san"] == "gxf3"
        assert text_of(events) == "The move was 5. gxf3."  # allowed now: nothing is withheld
        [info] = client.get(f"/api/games/{gid}").json()["moments"]
        assert (info["state"], info["best_san"], info["best_uci"]) == ("revealed", "gxf3", "g2f3")
        assert info["attempts"] == [
            {"uci": "a2a3", "san": "a3", "grade": "blunder"},
            {"uci": "h2h3", "san": "h3", "grade": "blunder"},
        ]

    def test_finding_the_move_solves_it(self) -> None:
        client, fake, app, gid = setup(INTRO, SOLVED)
        post(client, f"/api/games/{gid}/moments/1/start")

        events = attempt(client, gid, "g2f3", 0)

        assert moment_event(events) == {"grade": "best", "state": "solved"}
        assert payload(fake)["moment"]["best"]["san"] == "gxf3"
        assert progress(app).state == "solved"
        again = client.post(
            f"/api/games/{gid}/moments/1/attempt",
            json={"move_uci": "g2f3", "engine_after": after("g2f3", 0)},
        )
        assert again.status_code == 409

    def test_the_game_move_again_gets_no_hint(self) -> None:
        client, fake, _, gid = setup(INTRO, "That's what you played in the game. Let's look again.")
        post(client, f"/api/games/{gid}/moments/1/start")

        attempt(client, gid, "d1f3", -300)

        moment = payload(fake)["moment"]
        assert moment["same_as_game"] is True and moment["hints_allowed"] == []

    def test_moves_and_engine_results_are_checked(self) -> None:
        client, fake, _, gid = setup(INTRO)
        post(client, f"/api/games/{gid}/moments/1/start")
        url = f"/api/games/{gid}/moments/1/attempt"

        # No deep search of the moment's position yet (checked first: a valid one is kept).
        no_before = client.post(url, json={"move_uci": "a2a3", "engine_after": after("a2a3", 0)})
        illegal = client.post(url, json={"move_uci": "e1e3", "engine_before": BEFORE})
        no_after = client.post(url, json={"move_uci": "a2a3", "engine_before": BEFORE})
        wrong = client.post(url, json={"move_uci": "a2a3", "engine_after": after("h2h3", 0)})

        assert [r.status_code for r in (no_before, illegal, no_after, wrong)] == [
            409,
            422,
            409,
            422,
        ]
        assert progress_count(client, gid) == 0 and len(fake.requests) == 1  # nothing recorded


def progress_count(client: TestClient, gid: str) -> int:
    [info] = client.get(f"/api/games/{gid}").json()["moments"]
    return len(info["attempts"])


class TestDetail:
    def test_the_moments_position_has_no_engine_lines_until_revealed(self) -> None:
        client, _, _, gid = setup(INTRO, "Here's 5. gxf3.")
        post(client, f"/api/games/{gid}/moments/1/start")

        before = client.get(f"/api/games/{gid}").json()
        post(client, f"/api/games/{gid}/moments/1/reveal", {"engine_before": BEFORE})
        revealed = client.get(f"/api/games/{gid}").json()

        assert MOMENT_FEN not in [r["fen"] for r in before["engine_results"]]
        [info] = before["moments"]
        assert (info["state"], info["best_san"], info["san"]) == ("intro", None, "Qxf3")
        assert info["messages"] == [{"role": "coach", "text": INTRO, "kind": "intro"}]
        assert MOMENT_FEN in [r["fen"] for r in revealed["engine_results"]]

    def test_an_unopened_moment_is_new(self) -> None:
        client, _, _, gid = setup()

        [info] = client.get(f"/api/games/{gid}").json()["moments"]

        assert (info["state"], info["attempts"], info["messages"]) == ("new", [], [])


class TestQuestionsAndWrapUp:
    def test_a_question_after_a_failed_try_may_use_both_hints(self) -> None:
        client, fake, _, gid = setup(INTRO, FEEDBACK, "Think about which piece recaptures.")
        post(client, f"/api/games/{gid}/moments/1/start")
        attempt(client, gid, "a2a3", -300)

        post(client, f"/api/games/{gid}/moments/1/ask", {"message": "Can I get a hint?"})

        sent = payload(fake)
        assert sent["user_prompt"] == "Can I get a hint?"
        assert [h["level"] for h in sent["moment"]["hints_allowed"]] == [1, 2]
        assert "best" not in sent["moment"]

    def test_wrap_up_needs_every_moment_finished_and_is_stored(self) -> None:
        client, fake, _, gid = setup(INTRO, SOLVED, "Well done on all of them.")
        url = f"/api/games/{gid}/moments/wrap_up"
        assert client.post(url).status_code == 409
        post(client, f"/api/games/{gid}/moments/1/start")
        attempt(client, gid, "g2f3", 0)

        events = post(client, url)
        again = post(client, url)

        assert text_of(events) == text_of(again) == "Well done on all of them."
        assert len(fake.requests) == 3
        moment = payload(fake)["moment"]
        assert moment["wrap_up"] is True
        assert moment["results"] == [
            {"index": 1, "game_move": "5. Qxf3", "outcome": "solved", "attempts": 1}
        ]


def test_a_line_is_cut_before_a_withheld_move_not_dropped() -> None:
    """Real game (M4 checkpoint): the line after 8. Qb3 was 8...Qb6 9. h4 c5 10. Ne5, and 9. h4
    and 10. Ne5 were among the good 8th moves. The coach still sees 8...Qb6, what happens next."""
    from app.coach.moments import _scrub
    from app.coach.payload import MomentCandidate, MomentGameMove, MomentPayload

    moment = MomentPayload(
        index=1,
        of=1,
        state="attempt",
        game_move=MomentGameMove(
            san="8. Qb3",
            classification="mistake",
            eval_before="+2.2",
            eval_after="+0.8",
            themes=[],
            refutation_san=["Qb6", "h4", "c5", "Ne5", "c4", "Qxb6"],
        ),
        candidate=MomentCandidate(
            san="8. a3", grade="mistake", eval_after="+0.9", themes=[], refutation_san=["Ne5+"]
        ),
        attempt_number=1,
        max_attempts=2,
        reveal=False,
    )

    scrubbed = _scrub(moment, ["Ne5", "h4", "a4"])

    assert scrubbed.game_move.refutation_san == ["Qb6"]
    assert scrubbed.candidate is not None and scrubbed.candidate.refutation_san == []
    assert "Ne5" not in scrubbed.model_dump_json() and '"h4"' not in scrubbed.model_dump_json()
