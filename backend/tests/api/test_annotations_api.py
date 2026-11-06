"""Coach annotations end to end (SPEC_V3 §6, §11.1): board tags in chat, moment and synopsis
replies become `annotation` events, are stored with the message, and every dropped shape lands
in the annotation log. The leak check regenerates a moment answer once."""

from typing import Any

from fastapi import FastAPI

from app.db.chat import load_messages
from app.db.models import AnnotationLogRow
from tests.api.test_moments_api import INTRO, INTRO_SHOWN, post, progress, store_before, text_of
from tests.api.test_moments_api import setup as moment_setup
from tests.coach.test_chat import chat
from tests.coach.test_chat import setup as chat_setup


def annotation_events(events: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [data for name, data in events if name == "annotation"]


def log(app: FastAPI) -> list[tuple[str, str | None, str, int | None]]:
    with app.state.session_factory() as session:
        rows = session.query(AnnotationLogRow).order_by(AnnotationLogRow.id).all()
        return [(r.task, r.shape, r.reason, r.moment_index) for r in rows]


class TestChat:
    # The start position: the fake engine's four lines open with b1a3, b1c3, b2b3, b2b4, all
    # equal, so each grades "best"; the game went 1. e4 (in the data, ungraded: blue only).
    REPLY = 'Develop <board arrows="b1c3:green,g1f3:green,e2e4:green" squares="e4:blue"/> first.'

    def test_valid_shapes_are_sent_as_an_annotation_and_the_rest_logged(self) -> None:
        client, _, app, game_id = chat_setup(self.REPLY)

        events = chat(client, game_id, "What should I do here?")

        assert text_of(events) == "Develop [board](cc:board/0) first."
        assert annotation_events(events) == [
            {
                "tag_index": 0,
                "char_offset": 8,
                "arrows": [{"orig": "b1", "dest": "c3", "color": "green"}],
                "squares": [{"square": "e4", "color": "blue"}],
            }
        ]
        names = [name for name, _ in events]
        assert names.index("annotation") < names.index("done")
        assert log(app) == [
            ("chat", "g1f3:green", "not_in_data", None),
            ("chat", "e2e4:green", "wrong_color", None),
        ]

    def test_annotations_come_back_with_the_chat_and_the_coach_sees_its_own_tags(self) -> None:
        client, _, app, game_id = chat_setup(self.REPLY)
        chat(client, game_id, "What should I do here?")

        [_, coach] = client.get(f"/api/games/{game_id}").json()["chat"]

        assert coach["text"] == "Develop [board](cc:board/0) first."
        assert coach["annotations"][0]["arrows"] == [{"orig": "b1", "dest": "c3", "color": "green"}]
        with app.state.session_factory() as session:
            replayed = load_messages(session, game_id)[-1]["content"]
        raw = 'Develop <board arrows="b1c3:green" squares="e4:blue"/> first.'
        assert replayed == [{"type": "text", "text": raw}]

    def test_a_reply_without_tags_has_no_annotation_events(self) -> None:
        client, _, app, game_id = chat_setup("Just develop your pieces.")

        events = chat(client, game_id, "What now?")

        assert annotation_events(events) == []
        assert log(app) == []


class TestMoments:
    # 5. Qxf3 (d1f3) was the blunder; 5. gxf3 (g2f3) is the move the player must find.
    def test_marking_the_answer_is_a_leak_and_the_reply_is_regenerated(self) -> None:
        leaky = 'Look at <board squares="f3:green"/> carefully.'
        client, fake, app, gid = moment_setup(leaky, INTRO)
        store_before(app, gid)

        events = post(client, f"/api/games/{gid}/moments/1/start")

        assert text_of(events) == INTRO_SHOWN
        assert len(fake.requests) == 2
        note = fake.requests[1].messages[-1]["content"]
        assert isinstance(note, str) and "mark its squares" in note
        assert log(app) == [("moment_intro", "f3:green", "moment_leak", 1)]
        assert progress(app).leaks == 0

    def test_a_leak_that_survives_the_retry_is_dropped_and_counted(self) -> None:
        leaky = 'Your queen <board arrows="d1f3:red,g2f3:blue"/> went too far.'
        client, _, app, gid = moment_setup(leaky, leaky)
        store_before(app, gid)

        events = post(client, f"/api/games/{gid}/moments/1/start")

        [drawn] = annotation_events(events)
        assert drawn["arrows"] == [{"orig": "d1", "dest": "f3", "color": "red"}]
        assert progress(app).leaks == 1
        assert [entry[2] for entry in log(app)] == ["moment_leak", "moment_leak"]

    def test_the_games_mistake_may_be_drawn_and_comes_back_with_the_moment(self) -> None:
        reply = 'You played <board arrows="d1f3:red"/>. What else was there?'
        client, fake, app, gid = moment_setup(reply)
        store_before(app, gid)

        events = post(client, f"/api/games/{gid}/moments/1/start")
        again = post(client, f"/api/games/{gid}/moments/1/start")  # the stored intro

        assert text_of(events) == "You played [board](cc:board/0). What else was there?"
        assert annotation_events(again) == annotation_events(events)
        assert len(fake.requests) == 1
        [moment] = client.get(f"/api/games/{gid}").json()["moments"]
        assert moment["messages"][0]["annotations"] == annotation_events(events)
        assert log(app) == []


class TestSynopsis:
    def test_the_synopsis_has_no_board_position_so_tags_are_removed(self) -> None:
        client, _, app, game_id = chat_setup(
            'You opened well <board arrows="e2e4:blue"/>, then traded.'
        )

        response = client.post(f"/api/games/{game_id}/synopsis")

        assert "You opened well, then traded." in response.text
        assert "event: annotation" not in response.text
        assert log(app) == [("synopsis", None, "no_position", None)]
