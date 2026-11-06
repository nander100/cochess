"""Board annotations (SPEC_V3 §6.2), on hand-built positions: every arrow type and color, the
leak check, the limits, and the text the player and the coach history get."""

import chess
import pytest

from app.analysis.engine import EngineLine, EngineResult
from app.coach.annotations import (
    PLACEHOLDER,
    BoardFacts,
    annotate,
    engine_grades,
    plan_moves,
    san_to_keys,
)
from app.config import CoachSettings, Settings

# After 1. e4 e5 2. Nf3 Nc6 3. Bc4: Black to move. The bishop on c4 eyes f7.
FEN = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
LIMITS = CoachSettings()

FACTS = BoardFacts(
    fen=FEN,
    graded={"g8f6": "best", "f8c5": "good", "d7d6": "inaccuracy", "f7f5": "blunder", "a7a6": None},
    mistake="f7f5",
    plan_moves=frozenset({"f3g5", "g8f6"}),
)


def tag(arrows: str = "", squares: str = "") -> str:
    attrs = []
    if arrows:
        attrs.append(f'arrows="{arrows}"')
    if squares:
        attrs.append(f'squares="{squares}"')
    return f"<board {' '.join(attrs)}/>"


def check(arrows: str = "", squares: str = "", facts: BoardFacts | None = FACTS) -> list[str]:
    """The shapes that survive, as "fromto:color" / "square:color"."""
    result = annotate(f"Look {tag(arrows, squares)} here.", facts, LIMITS)
    kept = []
    for annotation in result.annotations:
        kept += [f"{a.orig}{a.dest}:{a.color}" for a in annotation.arrows]
        kept += [f"{s.square}:{s.color}" for s in annotation.squares]
    return kept


def reasons(arrows: str = "", squares: str = "", facts: BoardFacts | None = FACTS) -> list[str]:
    return [d.reason for d in annotate(tag(arrows, squares), facts, LIMITS).dropped]


# --- Move arrows ---


@pytest.mark.parametrize("arrow", ["g8f6:green", "f8c5:green", "g8f6:blue", "a7a6:blue"])
def test_a_good_move_from_the_data_may_be_green_or_blue(arrow: str) -> None:
    assert check(arrow) == [arrow]


def test_a_green_arrow_on_a_bad_move_is_rejected() -> None:
    assert check("f7f5:green") == []
    assert reasons("f7f5:green") == ["wrong_color"]
    assert reasons("d7d6:green") == ["wrong_color"]


def test_green_needs_a_known_good_grade() -> None:
    assert reasons("a7a6:green") == ["wrong_color"]  # in the data, but ungraded: blue only


def test_red_marks_a_mistake_or_the_games_own_mistake() -> None:
    assert check("f7f5:red") == ["f7f5:red"]
    graded_only = BoardFacts(fen=FEN, graded={"f7f5": "mistake"})
    assert check("f7f5:red", facts=graded_only) == ["f7f5:red"]
    game_move = BoardFacts(fen=FEN, graded={"f7f5": None}, mistake="f7f5")
    assert check("f7f5:red", facts=game_move) == ["f7f5:red"]
    assert reasons("g8f6:red") == ["wrong_color"]


def test_yellow_marks_only_an_inaccuracy() -> None:
    assert check("d7d6:yellow") == ["d7d6:yellow"]
    assert reasons("f8c5:yellow") == ["wrong_color"]


def test_a_legal_move_that_is_not_in_the_data_is_not_drawn() -> None:
    assert reasons("b7b6:blue") == ["not_in_data"]
    assert reasons("b7b6:green") == ["not_in_data"]


def test_a_move_from_the_data_that_is_illegal_here_is_not_drawn() -> None:
    facts = BoardFacts(fen=FEN, graded={"e8g8": "best"})  # Black can't castle yet
    assert reasons("e8g8:green", facts=facts) == ["not_in_data"]


def test_an_arrow_from_an_empty_square_is_illegal() -> None:
    assert reasons("a3a4:blue") == ["illegal_arrow"]
    assert reasons("e5e5:red") == ["illegal_arrow"]


# --- Threat and plan arrows ---


@pytest.mark.parametrize("arrow", ["c4f7:red", "c4f7:yellow", "f3e5:red"])
def test_a_threat_on_an_enemy_piece_may_be_red_or_yellow(arrow: str) -> None:
    assert check(arrow) == [arrow]  # White's threats, with Black to move


def test_the_side_to_moves_threats_count_too() -> None:
    # After 1. e4 d5: White to move, and Black's pawn on d5 attacks e4.
    fen = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    assert check("d5e4:red", facts=BoardFacts(fen=fen)) == ["d5e4:red"]


def test_controlling_an_empty_square_is_not_a_threat() -> None:
    assert reasons("c6d4:red") == ["not_in_data"]


@pytest.mark.parametrize("arrow", ["c4f7:green", "c4f7:blue"])
def test_a_threat_is_never_green_or_blue(arrow: str) -> None:
    assert reasons(arrow) == ["not_in_data"]


def test_an_arrow_to_a_square_the_piece_does_not_attack_is_not_a_threat() -> None:
    assert reasons("e4e5:red") == ["not_in_data"]  # a pawn doesn't attack straight ahead


def test_a_plan_arrow_is_blue_and_follows_the_engine_lines() -> None:
    assert check("f3g5:blue") == ["f3g5:blue"]
    assert reasons("f3h4:blue") == ["not_in_data"]
    assert reasons("f3g5:yellow") == ["not_in_data"]  # not a threat: g5 is empty


# --- Squares ---


@pytest.mark.parametrize("square", ["f7:red", "d4:yellow", "e5:green", "h1:blue"])
def test_any_square_may_be_highlighted(square: str) -> None:
    assert check(squares=square) == [square]


# --- Leak check ---

LEAKY = BoardFacts(
    fen=FEN,
    graded={"f7f5": "blunder", "a7a6": None},
    mistake="f7f5",
    banned=frozenset({"g8f6", "f8c5"}),
    known=frozenset({"f7f5"}),
)


@pytest.mark.parametrize(
    ("arrows", "squares"),
    [
        ("g8f6:blue", ""),  # the move itself
        ("g8e7:blue", ""),  # its from-square
        ("d8f6:blue", ""),  # its to-square
        ("", "f6:red"),
        ("", "c5:yellow"),
    ],
)
def test_pointing_out_a_move_the_player_must_find_is_a_leak(arrows: str, squares: str) -> None:
    assert reasons(arrows, squares, facts=LEAKY) == ["moment_leak"]
    assert annotate(tag(arrows, squares), LEAKY, LIMITS).leaked


def test_known_moves_and_unrelated_threats_are_not_leaks() -> None:
    assert check("f7f5:red,c4f7:red", facts=LEAKY) == ["f7f5:red", "c4f7:red"]
    assert not annotate(tag("f7f5:red"), LEAKY, LIMITS).leaked


def test_a_revealed_moment_has_no_leak_check() -> None:
    assert check("g8f6:green") == ["g8f6:green"]


# --- Limits and parsing ---


def test_at_most_four_arrows_and_four_squares_per_tag() -> None:
    arrows = "c4f7:red,c4f7:yellow,f3e5:red,f3g5:blue,g8f6:green"
    squares = "a1:red,a2:red,a3:red,a4:red,a5:red"
    result = annotate(tag(arrows, squares), FACTS, LIMITS)
    assert len(result.annotations[0].arrows) == 4
    assert len(result.annotations[0].squares) == 4
    assert [d.shape for d in result.dropped] == ["g8f6:green", "a5:red"]
    assert {d.reason for d in result.dropped} == {"too_many_shapes"}


def test_at_most_three_tags_per_message() -> None:
    text = " ".join(tag(squares=f"a{i}:red") for i in range(1, 5))
    result = annotate(text, FACTS, LIMITS)
    assert len(result.annotations) == 3
    assert [d.reason for d in result.dropped] == ["too_many_tags"]


@pytest.mark.parametrize(
    "raw",
    [
        '<board arrows="d1d4:purple"/>',
        '<board arrows="d1-d4:red"/>',
        '<board squares="z9:red"/>',
        '<board colour="red"/>',
        "<board/>",
        "<board arrows=d1d4:red/>",
    ],
)
def test_unreadable_tags_are_dropped_as_malformed(raw: str) -> None:
    result = annotate(f"See {raw} now", FACTS, LIMITS)
    assert result.annotations == []
    assert [d.reason for d in result.dropped] == ["malformed"]
    assert result.text == "See now"


def test_replies_without_a_position_lose_every_tag() -> None:
    result = annotate(f"Your opening {tag('c4f7:red')}, then the middlegame.", None, LIMITS)
    assert result.text == "Your opening, then the middlegame."
    assert [d.reason for d in result.dropped] == ["no_position"]


# --- Text ---


def test_valid_tags_become_placeholders_at_their_place() -> None:
    text = f"The bishop {tag('c4f7:red')} eyes f7, so {tag(squares='f7:yellow')} guard it."
    result = annotate(text, FACTS, LIMITS)
    assert result.text == (
        f"The bishop {PLACEHOLDER.format(index=0)} eyes f7, so "
        f"{PLACEHOLDER.format(index=1)} guard it."
    )
    for annotation in result.annotations:
        start = annotation.char_offset
        assert result.text[start:].startswith(f"[board](cc:board/{annotation.tag_index})")


def test_the_history_keeps_only_the_valid_shapes() -> None:
    result = annotate(f"Look {tag('c4f7:red,b7b6:green', 'f7:red')}.", FACTS, LIMITS)
    assert result.raw == 'Look <board arrows="c4f7:red" squares="f7:red"/>.'


def test_a_tag_with_nothing_valid_is_removed_cleanly() -> None:
    result = annotate(f"Careful {tag('b7b6:green')}, the bishop.", FACTS, LIMITS)
    assert result.text == "Careful, the bishop."
    assert result.raw == "Careful, the bishop."
    assert result.annotations == []


def test_stray_closing_tags_are_removed_silently() -> None:
    result = annotate("Here </board> it is.", FACTS, LIMITS)
    assert result.text == "Here it is."
    assert result.dropped == []


def test_text_without_tags_is_unchanged() -> None:
    text = "No board here, just 3...Nf6."
    result = annotate(text, FACTS, LIMITS)
    assert result.text == text
    assert result.raw == text
    assert result.annotations == []


# --- Facts ---


def engine(lines: list[tuple[int, list[str]]]) -> EngineResult:
    return EngineResult(
        fen=FEN,
        tier="deep",
        depth=20,
        time_ms=100,
        lines=[
            EngineLine(rank=i + 1, eval_cp=cp, moves_uci=moves)
            for i, (cp, moves) in enumerate(lines)
        ],
    )


def test_engine_lines_are_graded_against_the_best_line() -> None:
    settings = Settings()
    result = engine([(-20, ["g8f6", "f3g5"]), (-35, ["f8c5"]), (300, ["f7f5"]), (60, ["d7d6"])])
    grades = engine_grades(
        chess.Board(FEN), result, settings.thresholds, settings.moments.best_margin
    )
    assert grades["g8f6"] == "best"
    assert grades["f8c5"] in ("best", "good")
    assert grades["f7f5"] in ("mistake", "blunder")
    assert grades["d7d6"] != "best"
    assert plan_moves(result) == frozenset({"g8f6", "f3g5", "f8c5", "f7f5", "d7d6"})
    assert plan_moves(None) == frozenset()


def test_san_moves_become_keys_when_legal() -> None:
    assert san_to_keys(FEN, ["Nf6", "Bc5", "Qxh7", "nonsense"]) == frozenset({"g8f6", "f8c5"})
