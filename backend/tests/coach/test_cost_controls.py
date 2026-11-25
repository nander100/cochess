"""Cost controls (SPEC_V4 §9, M6): each task's system prompt carries only the shared rules it uses,
one-shot tasks aren't cached (a cache write costs more than it saves when nothing reads it), and
the model for each task and coach strength can be changed in config."""

import pytest
from pydantic import ValidationError

from app.coach.client import system_blocks, system_prompt
from app.config import Settings

BOARDLESS = ("synopsis", "baseline_report")
ON_A_BOARD = ("chat", "explain", "moment_intro", "moment_feedback", "walkthrough")


@pytest.mark.parametrize("task", BOARDLESS)
def test_a_write_up_without_a_board_skips_the_board_rules(task: str) -> None:
    prompt = system_prompt(task)  # type: ignore[arg-type]

    assert "# Annotations" not in prompt
    assert "# Position awareness" not in prompt
    assert "<board" not in prompt
    assert "no board tags" in prompt.lower()
    assert "# Hard rules" in prompt and "# How to talk about moves" in prompt


def test_the_baseline_report_still_says_no_line_links() -> None:
    assert "no line links" in system_prompt("baseline_report").lower()


@pytest.mark.parametrize("task", ON_A_BOARD)
def test_tasks_on_a_board_keep_every_shared_rule(task: str) -> None:
    prompt = system_prompt(task)  # type: ignore[arg-type]

    assert "# Annotations" in prompt
    assert "# Position awareness" in prompt


def test_the_write_ups_are_shorter_by_the_board_rules() -> None:
    core = len(system_prompt("chat").split()) - len(system_prompt("synopsis").split())
    assert core > 300  # the two sections are about 390 words


def test_system_blocks_are_cached_unless_asked_not_to() -> None:
    cached = system_blocks("chat", "the game")
    uncached = system_blocks("synopsis", cache=False)

    assert [b.get("cache_control") for b in cached] == [{"type": "ephemeral"}] * 2
    assert all("cache_control" not in b for b in uncached)
    assert uncached[0]["text"] == system_prompt("synopsis")


def test_every_task_is_cached_unless_config_says_otherwise() -> None:
    default = Settings(_env_file=None).coach
    chosen = Settings(_env_file=None, coach={"uncached_tasks": ["synopsis"]}).coach

    assert all(default.caches(task) for task in (*BOARDLESS, *ON_A_BOARD))
    assert not chosen.caches("synopsis") and chosen.caches("chat")


def test_each_task_has_its_model_by_strength_by_default() -> None:
    settings = Settings(_env_file=None)
    deep = settings.model_copy(update={"coach_tier": "deep"})

    assert settings.coach_model("synopsis") == "claude-sonnet-5-5"
    assert settings.coach_model("chat") == "claude-haiku-5-5"
    assert deep.coach_model("synopsis") == "claude-opus-5-5"
    assert deep.coach_model("chat") == "claude-sonnet-5-5"
    assert deep.coach_model("moment_intro") == "claude-haiku-5-5"


def test_a_tasks_model_can_be_changed_in_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COACH_ROUTES__STANDARD__SYNOPSIS", "claude-haiku-5-5")
    settings = Settings(_env_file=None)

    assert settings.coach_model("synopsis") == "claude-haiku-5-5"
    assert settings.coach_model("baseline_report") == "claude-sonnet-5-5"  # the rest unchanged
    deep = settings.model_copy(update={"coach_tier": "deep"})
    assert deep.coach_model("synopsis") == "claude-opus-5-5"


def test_a_route_to_an_unpriced_model_is_refused() -> None:
    with pytest.raises(ValidationError, match="no price"):
        Settings(_env_file=None, coach_routes={"standard": {"chat": "claude-mystery-9"}})


def test_a_route_for_an_unknown_task_or_strength_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, coach_routes={"standard": {"poetry": "claude-haiku-5-5"}})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, coach_routes={"turbo": {"chat": "claude-haiku-5-5"}})
