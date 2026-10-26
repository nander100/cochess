import json

import pytest

from app.analysis.pgn import parse_pgn
from app.coach.client import system_blocks, system_prompt
from app.coach.payload import (
    SYNOPSIS_INSTRUCTION,
    build_synopsis_payload,
    movetext,
    rating_band,
    render,
)
from tests.analysis.test_summary import opera_summary
from tests.pgn_fixtures import read_pgn

OPERA = parse_pgn(read_pgn("opera_game.pgn"), max_chars=100_000, max_plies=600)


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
    payload = build_synopsis_payload(opera_summary(), OPERA)

    assert payload.task == "synopsis"
    assert payload.player.model_dump() == {
        "elo": 1350,
        "color": "white",
        "rating_band": "intermediate",
        "playstyle": "attacking",
        "tendencies": [],
    }
    assert payload.pgn_to_move.startswith("1. e4 e5 2. Nf3 d6")
    assert payload.pgn_to_move.endswith("17. Rd8#")
    assert (payload.fen, payload.engine_lines, payload.user_prompt) == (None, None, None)


def test_render_sends_an_instruction_then_compact_json_without_the_eval_curve() -> None:
    text = render(build_synopsis_payload(opera_summary(), OPERA), SYNOPSIS_INSTRUCTION)

    instruction, body = text.split("\n\n", 1)
    data = json.loads(body)
    assert instruction == SYNOPSIS_INSTRUCTION
    assert "eval_curve" not in data["game_summary"]
    assert "move_list" in data["game_summary"]
    assert "fen" not in data and "user_prompt" not in data


def test_system_prompt_carries_the_hard_rules() -> None:
    prompt = system_prompt()

    assert "Never calculate, guess, or propose moves yourself" in prompt
    assert "the knight on f3" in prompt  # pieces and squares in words, not notation
    assert "hangingPiece" in prompt and "Lichess's puzzle trainer" in prompt
    assert "### Your turn" in prompt
    assert "at most 300 words in total" in prompt


def test_system_blocks_mark_only_the_last_block_for_caching() -> None:
    blocks = system_blocks("game summary block")

    assert [b.get("cache_control") for b in blocks] == [None, {"type": "ephemeral"}]
    assert blocks[0]["text"] == system_prompt()
