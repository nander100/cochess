"""Line links end to end (SPEC_V3 §9.4 to §9.6): resolved from the data, stored, played back with
a settle point and caption decided by the backend; withheld lines in an unsolved moment."""

from typing import Any

import chess

from app.db.models import LineLinkRow
from tests.api.test_moments_api import post, progress, store_before
from tests.api.test_moments_api import setup as moment_setup
from tests.auth_helpers import log_in
from tests.coach.test_chat import chat
from tests.coach.test_chat import setup as chat_setup
from tests.coach.test_synopsis import sse_events
from tests.engine_fakes import fake_result


def links(events: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [data for name, data in events if name == "line_link"]


def scans(link: dict[str, Any]) -> list[dict[str, Any]]:
    board = chess.Board()
    for uci in link["start_path_uci"]:
        board.push_uci(uci)
    fens = [board.fen()]
    for uci in link["moves_uci"]:
        board.push_uci(uci)
        fens.append(board.fen())
    return [fake_result(f, "scan", plies=1) for f in fens if not chess.Board(f).is_game_over()]


def test_a_chat_line_link_is_resolved_stored_and_played_back() -> None:
    client, _, app, game_id = chat_setup("Watch {{line:here.engine1|the engine's idea}} closely.")

    events = chat(client, game_id, "What's the plan?")

    [link] = links(events)
    assert (link["ref"], link["kind"], link["label"]) == (
        "here.engine1",
        "engine",
        "the engine's idea",
    )
    assert link["start_path_uci"] == [] and 1 <= len(link["moves_uci"]) <= 10
    played = client.post(
        f"/api/lines/{link['line_id']}/playback", json={"step_results": scans(link)}
    )
    assert played.status_code == 200, played.text
    body = played.json()
    assert body["moves_uci"] == link["moves_uci"]
    assert len(body["evals"]) == len(link["moves_uci"]) + 1
    assert 1 <= body["settle_ply"] <= len(link["moves_uci"])
    assert body["caption"]
    with app.state.session_factory() as session:
        row = session.get(LineLinkRow, link["line_id"])
        assert row is not None and (row.message, row.settle_ply) == ("chat", body["settle_ply"])
    [_, coach] = client.get(f"/api/games/{game_id}").json()["chat"]
    assert coach["line_links"][0]["line_id"] == link["line_id"]


def test_playback_belongs_to_its_player_and_checks_the_scans() -> None:
    client, _, app, game_id = chat_setup("See {{line:here.engine1|this}}.")
    [link] = links(chat(client, game_id, "Plan?"))
    url = f"/api/lines/{link['line_id']}/playback"

    assert log_in(app, "Stranger").post(url, json={"step_results": []}).status_code == 404
    elsewhere = fake_result("8/8/8/8/8/8/8/K6k w - - 0 1", "scan", plies=1)
    assert client.post(url, json={"step_results": [elsewhere]}).status_code == 422
    assert client.post(url, json={"step_results": []}).status_code == 200  # material only
    assert client.post("/api/lines/nope/playback", json={"step_results": []}).status_code == 404


def test_in_an_unsolved_moment_the_best_line_is_withheld_and_the_refutation_plays() -> None:
    leaky = "Here is {{line:here.best|the answer}}."
    fine = "Look at {{line:here.refutation|what happened after your move}}."
    client, fake, app, gid = moment_setup(leaky, fine)
    store_before(app, gid)

    events = post(client, f"/api/games/{gid}/moments/1/start")

    assert len(fake.requests) == 2  # the leak was regenerated
    [link] = links(events)
    assert (link["ref"], link["kind"], link["moves_uci"][0]) == (
        "here.refutation",
        "refutation",
        "d1f3",
    )
    assert progress(app).leaks == 0
    played = client.post(f"/api/lines/{link['line_id']}/playback", json={"step_results": []})
    assert played.json()["settle_ply"] >= min(3, len(link["moves_uci"]))  # 2 plies after the move


def test_a_synopsis_links_to_a_key_moment() -> None:
    client, _, _, game_id = chat_setup(
        "### Overall\nThe turning point: {{line:km1.refutation|see how it was punished}}."
    )

    events = sse_events(client.post(f"/api/games/{game_id}/synopsis").text)

    [link] = links(events)
    assert link["ref"] == "km1.refutation" and link["kind"] == "refutation"
    detail = client.get(f"/api/games/{game_id}").json()
    assert detail["synopsis"]["line_links"][0]["line_id"] == link["line_id"]


def test_deleting_the_game_removes_its_line_links() -> None:
    client, _, app, game_id = chat_setup("See {{line:here.engine1|this}}.")
    chat(client, game_id, "Plan?")

    assert client.delete(f"/api/games/{game_id}").status_code == 204

    with app.state.session_factory() as session:
        assert session.query(LineLinkRow).count() == 0
