"""The coach's markup (SPEC_V3 §9.4): move tags with backend words, line links resolved from
data, bare notation and moves in a row caught, leaks, and board tags in the same pass."""

from app.coach.annotations import BoardFacts
from app.coach.markup import REMOVED, ResolvedLine, Rules, note, process
from app.config import CoachSettings

LIMITS = CoachSettings()
ALLOWED = frozenset({"Nf3", "Nc6", "Bb5", "Qxd4", "O-O", "e8=Q", "exd5"})
LINES = {
    "here.engine1": ResolvedLine(("e2e4", "e7e5"), ("g1f3", "b8c6", "f1b5"), "engine"),
    "km2.refutation": ResolvedLine(("e2e4",), ("d7d5", "e4d5", "d8d5"), "refutation"),
}
RULES = Rules(allowed=ALLOWED, limits=LIMITS, lines=LINES)


def test_a_move_tag_becomes_words_with_its_token() -> None:
    done = process("Your {{move:Nf3}} develops, and {{move:O-O}} keeps the king safe.", RULES)

    assert done.text == (
        "Your [knight to f3](cc:move/0) develops, and [castles kingside](cc:move/1) keeps the "
        "king safe."
    )
    assert [(m.san, m.words, m.char_offset) for m in done.moves] == [
        ("Nf3", "knight to f3", 5), ("O-O", "castles kingside", 45)
    ]  # fmt: skip
    assert done.text[done.moves[1].char_offset :].startswith("[castles kingside](cc:move/1)")
    assert not done.problems.any
    assert done.raw == "Your {{move:Nf3}} develops, and {{move:O-O}} keeps the king safe."


def test_numbered_tags_keep_their_number_and_side() -> None:
    done = process("Black took with {{move:14...Qxd4}}, then 15. {{move:exd5}} came.", RULES)

    assert [(m.san, m.move_number, m.white) for m in done.moves] == [
        ("Qxd4", 14, False), ("exd5", 15, True)
    ]  # fmt: skip
    assert "15." not in done.text  # the number moved into the token
    assert done.raw == "Black took with {{move:14...Qxd4}}, then {{move:15.exd5}} came."


def test_a_promotion_gets_its_words() -> None:
    assert (
        process("Then {{move:e8=Q}}.", RULES).moves[0].words == "pawn to e8, promoting to a queen"
    )


def test_a_tag_naming_a_move_outside_the_data_is_removed() -> None:
    done = process("Try {{move:Qh5}} or {{move:nonsense}}.", RULES)

    assert done.text == f"Try {REMOVED} or {REMOVED}."
    assert done.problems.invalid == ["Qh5", "nonsense"]
    assert done.removed == ["Qh5", "nonsense"]


def test_bare_notation_is_a_problem_and_becomes_a_tag_when_valid() -> None:
    done = process("Your 2. Nf3 was fine but Qh5 was not.", RULES)

    assert done.problems.bare == ["Nf3", "Qh5"]
    assert done.problems.any
    assert done.text == f"Your [knight to f3](cc:move/0) was fine but {REMOVED} was not."
    assert (done.moves[0].move_number, done.moves[0].white) == (2, True)


def test_squares_in_prose_are_not_bare_moves() -> None:
    done = process("The knight on f3 and the e4 pawn control d5.", RULES)

    assert not done.problems.any and done.moves == []


def test_more_than_one_move_in_a_row_is_a_problem() -> None:
    assert (
        process("After {{move:Nf3}} {{move:Nc6}} {{move:Bb5}} it's even.", RULES).problems.runs == 2
    )
    assert process("{{move:14...Qxd4}} 15. {{move:exd5}}", RULES).problems.runs == 1
    one_at_a_time = process("After {{move:Nf3}}, Black answered with {{move:Nc6}}.", RULES)
    assert one_at_a_time.problems.runs == 0


def test_a_line_link_resolves_from_the_data() -> None:
    done = process("You can {{line:here.engine1|see what happens next}}.", RULES)

    [link] = done.line_links
    assert done.text == "You can [see what happens next](cc:line/0)."
    assert (link.ref, link.kind, link.label) == ("here.engine1", "engine", "see what happens next")
    assert link.start_path_uci == ["e2e4", "e7e5"]
    assert link.moves_uci == ["g1f3", "b8c6", "f1b5"]
    assert link.line_id and done.raw == "You can {{line:here.engine1|see what happens next}}."


def test_unknown_or_extra_line_links_keep_only_their_words() -> None:
    text = (
        "{{line:here.engine3|a}} {{line:km9.best|b}} {{line:there.engine1|c}} "
        "{{line:here.engine1|d}} {{line:km2.refutation|e}} {{line:here.engine1|f}} "
        "{{line:here.engine1|g}}"
    )
    done = process(text, RULES)

    assert [link.label for link in done.line_links] == ["d", "e", "f"]
    assert [d.reason for d in done.dropped] == ["unknown_line"] * 3 + ["too_many_links"]
    assert done.text.startswith("a b c [d](cc:line/0)")
    assert not done.problems.any  # dropped and logged, not regenerated


def test_best_before_reveal_is_a_leak() -> None:
    rules = Rules(allowed=ALLOWED, limits=LIMITS, lines=LINES, withheld=frozenset({"here.best"}))
    done = process("{{line:here.best|the answer}}", rules)

    assert done.problems.line_leaks == ["here.best"] and done.problems.leaked
    assert [d.reason for d in done.dropped] == ["moment_leak"]
    assert done.line_links == [] and done.text == "the answer"


def test_a_move_the_player_must_find_is_a_leak_unless_it_is_another_moves_number() -> None:
    rules = Rules(
        allowed=ALLOWED, limits=LIMITS, banned=frozenset({"Nf3"}), move_number=9,
        white_to_move=True,
    )  # fmt: skip
    leak = process("Play {{move:Nf3}}!", rules)
    earlier = process("Like {{move:2.Nf3}} earlier.", rules)
    bare = process("Nf3 wins.", rules)

    assert leak.problems.leaks == ["Nf3"] and leak.text == f"Play {REMOVED}!"
    assert not earlier.problems.leaked and earlier.moves[0].move_number == 2
    assert bare.problems.leaks == ["Nf3"] and bare.problems.leaked
    assert "Nf3" not in note(bare.problems)  # the retry note never names the answer


def test_a_move_with_the_wrong_number_is_removed() -> None:
    rules = Rules(allowed=ALLOWED, limits=LIMITS, numbering={"Nf3": {(2, True)}})
    done = process("{{move:5.Nf3}} and {{move:2.Nf3}}", rules)

    assert done.problems.misnumbered == ["Nf3"]
    assert [m.move_number for m in done.moves] == [2]


def test_board_tags_are_checked_in_the_same_pass() -> None:
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
    rules = Rules(allowed=ALLOWED, limits=LIMITS, facts=BoardFacts(fen=fen))
    done = process('Watch f7 <board arrows="c4f7:red"/> after {{move:Nc6}}.', rules)

    assert done.text == "Watch f7 [board](cc:board/0) after [knight to c6](cc:move/0)."
    assert done.annotations[0].char_offset == 9
    assert done.moves[0].char_offset == done.text.index("[knight")
    no_position = process('Watch <board arrows="c4f7:red"/>, then.', RULES)
    assert no_position.text == "Watch, then." and no_position.dropped[0].reason == "no_position"


def test_a_board_tag_that_leaks_is_a_problem() -> None:
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
    facts = BoardFacts(fen=fen, banned=frozenset({"g8f6"}))
    done = process('Look <board squares="f6:green"/>.', Rules(ALLOWED, LIMITS, facts=facts))

    assert done.problems.annotation_leak and done.problems.leaked


def test_unknown_curly_tags_are_dropped() -> None:
    done = process("A {{puzzle:fork}} idea.", RULES)
    assert done.text == "A  idea." and done.dropped[0].reason == "malformed"


def test_the_note_names_what_to_fix() -> None:
    problems = process("2. Nf3 Nc6 {{move:Qh5}} {{line:here.best|x}}", Rules(
        ALLOWED, LIMITS, lines=LINES, withheld=frozenset({"here.best"})
    )).problems  # fmt: skip
    text = note(problems)
    assert "not in the data: Qh5" in text
    assert "move tag" in text and "more than one move in a row" in text
    assert "supposed to find" in text and text.endswith("Rewrite the complete answer.")


def test_a_move_in_inline_code_is_bare_notation() -> None:
    done = process("Black answers with `Nc6` and then `exd5`; `the d-file` stays code.", RULES)

    assert done.problems.bare == ["Nc6", "exd5"]
    assert [m.san for m in done.moves] == ["Nc6", "exd5"]
    assert "`the d-file`" in done.text
    pawn_moves = process("`b5` and then `e4`", Rules(frozenset({"b5", "e4"}), LIMITS))
    assert pawn_moves.problems.bare == ["b5", "e4"]  # caught as notation, so rewritten once


def test_notation_in_a_link_label_is_bare_and_shown_in_words() -> None:
    done = process("{{line:here.engine1|see the line after exd5 and Qh5}}", RULES)

    assert done.problems.bare == ["exd5", "Qh5"]
    assert done.line_links[0].label == "see the line after pawn takes on d5 and"
    assert done.removed == ["Qh5"]


def test_a_move_that_begins_a_sentence_is_marked() -> None:
    done = process(
        "{{move:Nf3}} develops. Then {{move:Nc6}}. And:\n- {{move:Bb5}} pins? "
        "**{{move:O-O}}** too.",
        RULES,
    )

    assert [m.sentence_start for m in done.moves] == [True, False, True, True]


def test_a_move_tag_in_code_formatting_still_counts() -> None:
    done = process("The best move is `{{move:Nf3}}`, not `{{move:Qh5}}`.", RULES)

    assert done.text == f"The best move is [knight to f3](cc:move/0), not {REMOVED}."
    assert done.problems.invalid == ["Qh5"] and done.problems.bare == []


def test_at_the_plain_level_evaluation_numbers_are_a_problem_and_bracketed_ones_go() -> None:
    plain = Rules(ALLOWED, LIMITS, words_only_evals=True)
    done = process("You were slightly better (+0.6), then -1.1 after {{move:Nf3}}.", plain)

    assert done.problems.evals == ["(+0.6)", "-1.1"]
    assert done.text.startswith("You were slightly better, then -1.1 after")
    assert "plain" in note(done.problems)
    assert not process("You were slightly better (+0.6).", RULES).problems.any  # other levels
