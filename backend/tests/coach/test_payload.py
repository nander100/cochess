import json

import pytest

from app.analysis.pgn import parse_pgn
from app.coach.client import system_blocks, system_prompt
from app.coach.payload import (
    SYNOPSIS_INSTRUCTION,
    annotated_movetext,
    build_synopsis_payload,
    coach_view,
    movetext,
    rating_band,
    render,
)
from app.config import CoachSettings
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
    }
    assert payload.pgn_to_move is not None
    assert payload.pgn_to_move.startswith("1. e4 e5 2. Nf3 d6")
    assert payload.pgn_to_move.endswith("17. Rd8#")
    assert (payload.fen, payload.engine_lines, payload.user_prompt) == (None, None, None)


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


def test_system_blocks_mark_only_the_last_block_for_caching() -> None:
    blocks = system_blocks("chat", "game summary block")

    assert [b.get("cache_control") for b in blocks] == [None, {"type": "ephemeral"}]
    assert blocks[0]["text"] == system_prompt("chat")


def test_each_task_gets_only_its_own_instructions() -> None:
    synopsis, chat = system_prompt("synopsis"), system_prompt("chat")

    assert "Never calculate, guess, or propose moves yourself" in synopsis
    assert "Never calculate, guess, or propose moves yourself" in chat
    assert "### Your turn" in synopsis and "with the ply of the position" not in synopsis
    assert "with the ply of the position" in chat and "### Your turn" not in chat


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
