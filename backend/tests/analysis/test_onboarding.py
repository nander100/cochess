"""Onboarding (SPEC_V2 §10): splitting pastes, time-control categories, and slots."""

from typing import Any

import pytest

from app.analysis.onboarding import Candidate, assign_slots, split_games, time_control_category
from app.analysis.pgn import PgnError
from app.config import Limits, OnboardingSettings
from tests.pgn_fixtures import USER_FIXTURES

SETTINGS = OnboardingSettings()
LIMITS = Limits()


@pytest.mark.parametrize(
    ("header", "category"),
    [
        ("15", "bullet"),  # ultrabullet counts as bullet
        ("60+0", "bullet"),
        ("120+1", "bullet"),  # 120 + 40 = 160 s
        ("180", "blitz"),
        ("180+2", "blitz"),  # 260 s
        ("300+5", "rapid"),  # 500 s
        ("600", "rapid"),
        ("900+10", "rapid"),  # 1300 s
        ("1500", "classical"),
        ("1800+20", "classical"),
        ("1/259200", "correspondence"),
        ("-", None),
        ("?", None),
        ("", None),
        (None, None),
    ],
)
def test_time_control_categories(header: str | None, category: str | None) -> None:
    assert time_control_category(header, SETTINGS) == category


class TestSplit:
    def test_the_owners_exports_split_into_games(self) -> None:
        paste = "\n\n".join(path.read_text() for path in USER_FIXTURES)

        games = split_games(paste, LIMITS, SETTINGS)

        assert len(games) == len(USER_FIXTURES)
        assert all(g.game is not None and g.error is None for g in games)
        assert [g.game.headers["Black"] for g in games if g.game] == [
            path.read_text().split('[Black "')[1].split('"')[0] for path in USER_FIXTURES
        ]

    def test_games_without_headers_split_after_their_result(self) -> None:
        games = split_games("1. e4 e5 1-0\n1. d4 d5 2. c4 *\n\n1. c4 0-1", LIMITS, SETTINGS)

        assert [len(g.game.positions) for g in games if g.game] == [2, 3, 1]

    def test_a_bad_game_is_reported_and_the_rest_still_parse(self) -> None:
        paste = (
            '[Event "a"]\n\n1. e4 e5 *\n\n'
            '[Event "b"]\n[SetUp "1"]\n[FEN "8/8/8/8/8/8/8/K6k w - - 0 1"]\n\n1. Kb1 *\n\n'
            '[Event "c"]\n\n1. e4 e4 *\n'
        )

        games = split_games(paste, LIMITS, SETTINGS)

        assert [g.error.code if g.error else None for g in games] == [
            None,
            "non_standard_start",
            "illegal_move",
        ]

    def test_blank_space_is_not_a_game(self) -> None:
        assert len(split_games("\n\n1. e4 *\n\n\n", LIMITS, SETTINGS)) == 1

    def test_too_many_games_in_one_paste(self) -> None:
        paste = "\n".join("1. e4 *" for _ in range(SETTINGS.max_paste_games + 1))

        with pytest.raises(PgnError, match="at most 40 games"):
            split_games(paste, LIMITS, SETTINGS)

    def test_too_much_text(self) -> None:
        small = OnboardingSettings(max_paste_chars=10)

        with pytest.raises(PgnError, match="too much text"):
            split_games("1. e4 e5 2. Nf3 *", LIMITS, small)


def candidate(**overrides: Any) -> Candidate:
    fields: dict[str, Any] = {"color": "white", "result": "win", "category": "rapid"}
    return Candidate(**{**fields, **overrides})


class TestSlots:
    def test_each_color_and_result_has_its_own_slot(self) -> None:
        candidates = [
            candidate(color="white", result="win"),
            candidate(color="white", result="loss"),
            candidate(color="black", result="win"),
            candidate(color="black", result="loss"),
        ]

        decisions = assign_slots({}, candidates, "rapid", SETTINGS)

        assert [d.slot for d in decisions] == ["white_win", "white_loss", "black_win", "black_loss"]
        assert all(d.reason is None for d in decisions)

    def test_a_slot_takes_three_games_counting_ones_already_filled(self) -> None:
        decisions = assign_slots({"white_win": 1}, [candidate()] * 3, "rapid", SETTINGS)

        assert [(d.slot, d.reason) for d in decisions] == [
            ("white_win", None),
            ("white_win", None),
            (None, "slot_full"),
        ]

    @pytest.mark.parametrize(
        ("overrides", "reason"),
        [
            ({"result": "draw"}, "draw"),
            ({"result": None}, "unfinished"),
            ({"category": "blitz"}, "wrong_time_control"),
            ({"category": "correspondence"}, "wrong_time_control"),
            ({"category": None}, "needs_time_control"),
            ({"color": None}, "needs_color"),
            ({"duplicate": True}, "duplicate"),
            ({"invalid": True, "color": None}, "invalid_pgn"),
        ],
    )
    def test_games_that_fill_no_slot_say_why(self, overrides: dict[str, Any], reason: str) -> None:
        (decision,) = assign_slots({}, [candidate(**overrides)], "rapid", SETTINGS)

        assert (decision.slot, decision.reason) == (None, reason)

    def test_a_rejected_game_doesnt_use_up_a_slot(self) -> None:
        candidates = [candidate(result="draw"), candidate(), candidate(), candidate()]

        decisions = assign_slots({}, candidates, "rapid", SETTINGS)

        assert [d.slot for d in decisions] == [None, "white_win", "white_win", "white_win"]
