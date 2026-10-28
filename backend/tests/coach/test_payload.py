import json
from typing import Any

import pytest

from app.analysis.detectors.types import ThemeName
from app.analysis.pgn import parse_pgn
from app.analysis.tendencies import (
    THEME_LABELS,
    AccuracyReport,
    Example,
    Tendency,
    TendencyReport,
)
from app.coach.client import history_breakpoint, system_blocks, system_prompt, task_instructions
from app.coach.payload import (
    SYNOPSIS_INSTRUCTION,
    annotated_movetext,
    build_synopsis_payload,
    coach_view,
    movetext,
    player_payload,
    rating_band,
    render,
    with_tendencies,
)
from app.coach.validate import allowed_moves, find_invalid
from app.config import CoachSettings, TendencySettings
from tests.analysis.test_summary import opera_summary
from tests.pgn_fixtures import read_pgn

OPERA = parse_pgn(read_pgn("opera_game.pgn"), max_chars=100_000, max_plies=600)
COACH = CoachSettings()


@pytest.mark.parametrize(
    ("elo", "band"),
    [(100, "beginner"), (999, "beginner"), (1000, "intermediate"), (1800, "intermediate"),
     (1801, "advanced"), (2500, "advanced")],
)  # fmt: skip
def test_rating_bands(elo: int, band: str) -> None:
    assert rating_band(elo) == band


def test_movetext_numbers_white_moves() -> None:
    game = parse_pgn("1. e4 e5 2. Nf3 Nc6 3. Bb5 *", max_chars=1000, max_plies=10)

    assert movetext(game.positions) == "1. e4 e5 2. Nf3 Nc6 3. Bb5"


def test_synopsis_payload_has_the_full_game_and_summary_but_no_position() -> None:
    payload = build_synopsis_payload(opera_summary(), COACH)

    assert payload.task == "synopsis"
    assert payload.player.model_dump() == {
        "elo": 1350,
        "color": "white",
        "rating_band": "intermediate",
        "playstyle": "attacking",
        "tendencies": [],
        "accuracy_by_phase": None,
        "accuracy_by_color": None,
    }
    assert payload.pgn_to_move is not None
    assert payload.pgn_to_move.startswith("1. e4 e5 2. Nf3 d6")
    assert payload.pgn_to_move.endswith("17. Rd8#")
    assert (payload.position, payload.engine_lines, payload.user_prompt) == (None, None, None)


def test_render_sends_an_instruction_then_compact_json_without_the_eval_curve() -> None:
    text = render(build_synopsis_payload(opera_summary(), COACH), SYNOPSIS_INSTRUCTION)

    instruction, body = text.split("\n\n", 1)
    data = json.loads(body)
    assert instruction == SYNOPSIS_INSTRUCTION
    assert "eval_curve" not in data["game_summary"]
    assert "move_list" not in data["game_summary"]  # its labels are in pgn_to_move
    assert "fen" not in data and "user_prompt" not in data


def test_system_prompt_carries_the_hard_rules() -> None:
    prompt = system_prompt("synopsis")

    assert "Never calculate, guess, or propose moves yourself" in prompt
    assert "the knight on f3" in prompt  # pieces and squares in words, not notation
    assert "hangingPiece" in prompt and "Lichess's puzzle trainer" in prompt
    assert "### Your turn" in prompt
    assert "at most 300 words in total" in prompt
    assert "Do reason about the position" in prompt  # owner, M5 review
    assert "The engine is the authority on moves and evaluations" in prompt


def test_system_blocks_cache_the_prompt_and_the_game_context_separately() -> None:
    blocks = system_blocks("chat", "game summary block")

    # Two breakpoints: the prompt is shared by every game's chat; the context by this game's calls.
    assert [b.get("cache_control") for b in blocks] == [{"type": "ephemeral"}] * 2
    assert [b["text"] for b in blocks] == [system_prompt("chat"), "game summary block"]


def test_the_history_breakpoint_marks_the_message_before_the_newest() -> None:
    messages: list[Any] = [
        {"role": "user", "content": [{"type": "text", "text": "first question"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "first answer"}]},
        {"role": "user", "content": "new question"},
    ]

    marked = history_breakpoint(messages)

    assert marked[1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in str(marked[0]) and "cache_control" not in str(marked[2])
    assert "cache_control" not in str(messages)  # the stored history is never changed


def test_no_history_breakpoint_on_a_first_message_or_after_thinking() -> None:
    first: list[Any] = [{"role": "user", "content": "only question"}]
    thinking: list[Any] = [
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "..."}]},
        {"role": "user", "content": "next"},
    ]

    assert "cache_control" not in str(history_breakpoint(first))
    assert "cache_control" not in str(history_breakpoint(thinking))


def test_a_string_message_is_turned_into_a_block_for_its_breakpoint() -> None:
    messages: list[Any] = [
        {"role": "user", "content": "question"},
        {"role": "user", "content": "follow-up"},
    ]

    assert history_breakpoint(messages)[0]["content"] == [
        {"type": "text", "text": "question", "cache_control": {"type": "ephemeral"}}
    ]


def test_each_task_gets_only_its_own_instructions() -> None:
    synopsis, chat = system_prompt("synopsis"), system_prompt("chat")
    explain = task_instructions("explain")  # sent in Explain's user turn, on the chat prompt

    for prompt in (synopsis, chat):
        assert "Never calculate, guess, or propose moves yourself" in prompt
        assert "The `position` object is what the player sees on the board" in prompt
    assert "### Your turn" in synopsis
    assert "candidate_moves_san" in chat
    assert "Where things stand" in explain and "Never calculate" not in explain
    assert "### Your turn" not in chat + explain and "candidate_moves_san" not in synopsis + explain


def test_annotated_movetext_marks_each_labelled_move() -> None:
    # White's 6th move (ply 11) is a blunder in this summary.
    text = annotated_movetext(opera_summary({ply: -300 for ply in range(12, 34)}))

    assert text.startswith("1. e4 e5 2. Nf3 d6")
    assert "6. Bc4?? Nf6" in text
    assert text.endswith("17. Rd8#")


def test_coach_view_trims_engine_lines_but_not_the_stored_summary() -> None:
    summary = opera_summary({ply: -300 for ply in range(12, 34)})

    view = coach_view(summary, CoachSettings(coach_engine_lines=1, coach_line_plies=2))

    for moment, original in zip(view.key_moments, summary.key_moments, strict=True):
        assert len(moment.engine_lines) == 1
        assert all(len(line.moves_san) <= 2 for line in moment.engine_lines)
        assert len(moment.line_after_san) <= 2
        assert len(original.engine_lines) == 2  # opera_summary asks for 2 lines


EXAMPLES = ["Nd4", "Bc4", "Qh5", "Re1", "Kf2", "a4", "g4"]


def _report(themes: int) -> TendencyReport:
    names: list[ThemeName] = ["hung_piece", "allowed_tactic", "missed_tactic", "king_safety",
                              "pawn_structure", "endgame_technique", "time_trouble"]  # fmt: skip
    return TendencyReport(
        games_analyzed=6,
        provisional=False,
        tendencies=[
            Tendency(
                theme=name,
                label=THEME_LABELS[name],
                rate_per_game=1.0,
                score=7.0 - i,
                trend=None,
                games_seen=3,
                provisional=False,
                recent_example=Example(game_id="g", move_number=14, move_san=EXAMPLES[i]),
            )
            for i, name in enumerate(names[:themes])
        ],
        accuracy=AccuracyReport(
            overall=80.0,
            by_color={"white": 82.0, "black": 78.0},
            by_phase={"opening": 90.0, "middlegame": 75.0, "endgame": None},
        ),
    )


def test_the_coach_gets_the_top_tendencies_without_their_scores() -> None:
    player = with_tendencies(player_payload(opera_summary()), _report(7), TendencySettings())

    assert [t.theme for t in player.tendencies] == [
        "hung_piece", "allowed_tactic", "missed_tactic", "king_safety", "pawn_structure",
    ]  # fmt: skip
    assert player.model_dump(mode="json")["tendencies"][0] == {
        "theme": "hung_piece",
        "label": "Leaving pieces undefended",
        "rate_per_game": 1.0,
        "trend": None,
        "games_seen": 3,
        "provisional": False,
        "recent_example": {"game_id": "g", "move_number": 14, "move_san": "Nd4"},
    }
    assert player.accuracy_by_phase == {"opening": 90.0, "middlegame": 75.0, "endgame": None}
    assert player.accuracy_by_color == {"white": 82.0, "black": 78.0}


def test_no_tendencies_before_any_game_is_analyzed() -> None:
    player = player_payload(opera_summary())
    empty = _report(0).model_copy(update={"games_analyzed": 0})

    assert with_tendencies(player, None, TendencySettings()) == player
    assert with_tendencies(player, empty, TendencySettings()) == player


def test_a_tendencys_example_move_is_allowed() -> None:
    player = with_tendencies(player_payload(opera_summary()), _report(1), TendencySettings())
    payload = build_synopsis_payload(opera_summary(), COACH, player)

    allowed = allowed_moves(payload.model_dump(mode="json"))
    assert "Nd4" in allowed
    assert find_invalid("Like Nd4 in your last game.", allowed) == []


def test_in_a_moment_an_example_that_matches_the_answer_loses_its_move() -> None:
    from app.coach.moments import _scrub_player

    player = with_tendencies(player_payload(opera_summary()), _report(2), TendencySettings())

    scrubbed = _scrub_player(player, ["Bc4"])

    examples = [t.recent_example.model_dump() for t in scrubbed.tendencies]
    assert examples == [
        {"game_id": "g", "move_number": 14, "move_san": "Nd4"},
        {"game_id": "g", "move_number": None, "move_san": None},
    ]
