"""Line walkthroughs end to end (SPEC_V3 §7) with a scripted coach: the forced tool call, the
checks (one step per ply, moves from the data, per-step shapes on the position after the move),
regeneration, the cache, and the critical-moment guard."""

from typing import Any

import chess
from fastapi.testclient import TestClient

from app.db.models import (
    AnnotationLogRow,
    Game,
    LlmUsageRow,
    MomentProgressRow,
    WalkthroughRow,
)
from tests.api.test_moments_api import MOMENT_FEN, store_before
from tests.api.test_moments_api import setup as moment_setup
from tests.auth_helpers import log_in
from tests.coach.test_chat import setup as chat_setup
from tests.coach.test_synopsis import sse_events
from tests.coach_fakes import ToolCall
from tests.engine_fakes import fake_result

START = ["e2e4", "e7e5"]  # the Opera Game went 1. e4 e5 2. Nf3 d6 3. d4
LINE = ["g1f3", "d7d6", "d2d4"]


def fens(start: list[str], line: list[str]) -> list[str]:
    board = chess.Board()
    for uci in start:
        board.push_uci(uci)
    out = [board.fen()]
    for uci in line:
        board.push_uci(uci)
        out.append(board.fen())
    return out


def scans(start: list[str] = START, line: list[str] = LINE) -> list[dict[str, Any]]:
    return [fake_result(fen, "scan", plies=1) for fen in fens(start, line)]


def tool(steps: list[dict[str, Any]], intro: str = "A calm developing line.") -> ToolCall:
    return ToolCall(
        input={"intro": intro, "steps": steps, "summary": "Develop with tempo."},
        name="line_walkthrough",
    )


GOOD = tool(
    [
        {"index": 1, "text": "2. Nf3 attacks the e5 pawn.", "arrows": ["f3e5:red", "d7d6:blue",
                                                                       "h1h8:red"]},
        {"index": 2, "text": "Black defends it.", "squares": ["e5:green"]},
        {"index": 3, "text": "3. d4 strikes at the centre."},
    ]
)  # fmt: skip


def ask(client: TestClient, game_id: str, **overrides: Any) -> Any:
    body = {"start_path_uci": START, "line_uci": LINE, "step_results": scans(), **overrides}
    return client.post(f"/api/games/{game_id}/walkthrough", json=body)


def walkthrough_of(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    events = sse_events(response.text)
    assert events[-1][0] == "done", events
    [data] = [d for name, d in events if name == "walkthrough"]
    return data


def test_a_line_is_walked_through_step_by_step() -> None:
    client, fake, app, game_id = chat_setup(GOOD)

    walk = walkthrough_of(ask(client, game_id))

    [request] = fake.requests
    assert [t["name"] for t in request.tools] == ["line_walkthrough"]
    assert request.tool_choice == {"type": "tool", "name": "line_walkthrough"}
    assert "walk the player through a line" in request.system[0]["text"]
    sent = request.messages[0]["content"]
    assert isinstance(sent, str) and '"walkthrough"' in sent and '"newly_attacked"' in sent
    assert walk["start_path_uci"] == START and walk["line_uci"] == LINE
    assert [s["san"] for s in walk["steps"]] == ["Nf3", "d6", "d4"]
    assert [s["fen_after"] for s in walk["steps"]] == fens(START, LINE)[1:]
    assert walk["steps"][0]["text"] == "2. Nf3 attacks the e5 pawn."
    assert walk["steps"][0]["eval_after"] == "0.0" and walk["steps"][0]["win_pct_after"] == 50.0
    # Shapes are checked on the position after the step's move: the knight's threat and the
    # line's next move pass; an arrow that's neither is dropped and logged.
    assert walk["steps"][0]["annotation"]["arrows"] == [
        {"orig": "f3", "dest": "e5", "color": "red"},
        {"orig": "d7", "dest": "d6", "color": "blue"},
    ]
    assert walk["steps"][1]["annotation"]["squares"] == [{"square": "e5", "color": "green"}]
    assert walk["steps"][2]["annotation"] is None
    with app.state.session_factory() as session:
        assert session.query(LlmUsageRow).one().task == "walkthrough"
        [dropped] = session.query(AnnotationLogRow).all()
        assert (dropped.task, dropped.shape, dropped.reason) == ("walkthrough", "h1h8:red",
                                                                 "not_in_data")  # fmt: skip


def test_the_same_line_again_comes_from_the_cache() -> None:
    client, fake, _, game_id = chat_setup(GOOD)
    first = walkthrough_of(ask(client, game_id))

    again = walkthrough_of(ask(client, game_id, step_results=[]))

    assert again == first
    assert len(fake.requests) == 1


def test_the_wrong_number_of_steps_is_regenerated_once() -> None:
    short = tool([{"index": 1, "text": "Develop."}])
    client, fake, _, game_id = chat_setup(short, GOOD)

    walk = walkthrough_of(ask(client, game_id))

    assert len(walk["steps"]) == 3 and len(fake.requests) == 2
    retry = fake.requests[1].messages
    assert retry[1]["role"] == "assistant"
    [result] = retry[2]["content"]  # type: ignore[misc]
    assert result["type"] == "tool_result" and result["is_error"] is True
    assert "indexed 1 to 3" in result["content"]


def test_a_walkthrough_that_stays_wrong_is_an_error() -> None:
    short = tool([{"index": 1, "text": "Develop."}])
    client, _, app, game_id = chat_setup(short, short)

    events = sse_events(ask(client, game_id).text)

    assert events[-1] == ("error", {"message": "The coach couldn't put this walkthrough together. "
                                               "Please try again."})  # fmt: skip
    with app.state.session_factory() as session:
        assert session.query(WalkthroughRow).count() == 0


def test_a_reply_without_the_tool_is_retried() -> None:
    client, fake, _, game_id = chat_setup("Here is the line in words.", GOOD)

    walkthrough_of(ask(client, game_id))

    note = fake.requests[1].messages[2]
    assert note["role"] == "user" and isinstance(note["content"], str)
    assert "no line_walkthrough call" in note["content"]


def test_moves_outside_the_data_are_regenerated_then_removed() -> None:
    bad = tool([{"index": 1, "text": "Better was Qh5."}, {"index": 2, "text": "Fine."},
                {"index": 3, "text": "Then Qh5 again."}])  # fmt: skip
    client, fake, _, game_id = chat_setup(bad, bad)

    walk = walkthrough_of(ask(client, game_id))

    assert len(fake.requests) == 2
    assert walk["invalid_moves_removed"] == ["Qh5"]
    assert walk["steps"][0]["text"] == "Better was [move removed]."


def test_bad_requests_are_refused_before_the_coach_is_called() -> None:
    client, fake, _, game_id = chat_setup()

    assert ask(client, game_id, line_uci=["g1f3", "e7e5"]).status_code == 422  # illegal
    assert ask(client, game_id, line_uci=["a2a3"] * 11).status_code == 422  # too long
    assert ask(client, game_id, step_results=scans()[:2]).status_code == 422  # not all scanned
    deep = [fake_result(fen, "deep", plies=1, lines=9) for fen in fens(START, LINE)]
    assert ask(client, game_id, step_results=deep).status_code == 422  # more lines than allowed
    assert fake.requests == []


def test_another_players_game_is_not_found() -> None:
    _, _, app, game_id = chat_setup()
    stranger = log_in(app, "Stranger")

    assert ask(stranger, game_id).status_code == 404


def moment_body(client: TestClient, gid: str, line: list[str]) -> dict[str, Any]:
    path = [m["uci"] for m in client.get(f"/api/games/{gid}").json()["moves"][:8]]
    board = chess.Board()
    for uci in path:
        board.push_uci(uci)
    assert board.fen() == MOMENT_FEN  # before 5. Qxf3, the game's blunder
    return {"start_path_uci": path, "line_uci": line, "step_results": []}


def test_an_unsolved_moments_best_line_is_withheld() -> None:
    client, fake, app, gid = moment_setup()
    store_before(app, gid)

    refused = client.post(f"/api/games/{gid}/walkthrough", json=moment_body(client, gid, ["g2f3"]))

    assert refused.status_code == 409 and "Solve or reveal" in refused.json()["detail"]
    # A poor move from there gives nothing away (this one only lacks its scans).
    other = client.post(f"/api/games/{gid}/walkthrough", json=moment_body(client, gid, ["a2a3"]))
    assert other.status_code == 422
    assert fake.requests == []


def test_a_revealed_moments_best_line_can_be_walked_through() -> None:
    one_step = tool([{"index": 1, "text": "5. gxf3 takes back with the pawn."}])
    client, _, app, gid = moment_setup(one_step)
    store_before(app, gid)
    with app.state.session_factory() as session:
        owner = session.get(Game, gid)
        assert owner is not None and owner.user_id is not None
        session.add(MomentProgressRow(user_id=owner.user_id, game_id=gid, moment_index=1,
                                      state="revealed", attempts=[], revealed=True,
                                      messages=[]))  # fmt: skip
        session.commit()
    body = moment_body(client, gid, ["g2f3"])
    body["step_results"] = scans(body["start_path_uci"], ["g2f3"])

    walk = walkthrough_of(client.post(f"/api/games/{gid}/walkthrough", json=body))

    assert [s["san"] for s in walk["steps"]] == ["gxf3"]


def test_deleting_or_recoloring_the_game_clears_its_walkthroughs() -> None:
    client, _, app, game_id = chat_setup(GOOD)
    walkthrough_of(ask(client, game_id))

    assert client.patch(f"/api/games/{game_id}", json={"user_color": "black"}).status_code == 200

    with app.state.session_factory() as session:
        assert session.query(WalkthroughRow).count() == 0


def test_a_line_that_ends_in_mate_needs_no_search_of_the_mate() -> None:
    mate = tool([{"index": 1, "text": "The rook mates."}])
    client, _, _, game_id = chat_setup(mate)
    moves = [m["uci"] for m in client.get(f"/api/games/{game_id}").json()["moves"]]
    start, line = moves[:-1], moves[-1:]  # the Opera Game ends 17. Rd8#
    only_start = scans(start, line)[:1]

    walk = walkthrough_of(ask(client, game_id, start_path_uci=start, line_uci=line,
                              step_results=only_start))  # fmt: skip

    assert walk["steps"][0]["san"] == "Rd8#"
    assert walk["steps"][0]["eval_after"] == "+M0" and walk["steps"][0]["win_pct_after"] == 100


def test_tool_input_that_breaks_the_schema_is_retried() -> None:
    broken = ToolCall(input={"steps": "three"}, name="line_walkthrough")
    client, fake, _, game_id = chat_setup(broken, GOOD)

    walkthrough_of(ask(client, game_id))

    assert "doesn't match the schema" in str(fake.requests[1].messages[2]["content"])


def test_new_walkthroughs_per_game_are_limited() -> None:
    client, fake, app, game_id = chat_setup()
    app.state.settings.coach.walkthrough_max_per_game = 0

    response = ask(client, game_id)

    assert response.status_code == 429 and fake.requests == []
