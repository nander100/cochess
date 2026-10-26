import pytest

from app.config import EngineTier, Settings


def test_engine_tiers_match_spec_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.engine.scan == EngineTier(
        multipv=1, min_time_ms=250, min_depth=12, hard_cap_ms=1000, max_line_plies=1
    )
    assert settings.engine.verify == EngineTier(
        multipv=4, min_time_ms=1500, min_depth=18, hard_cap_ms=3000, max_line_plies=10
    )
    assert settings.engine.deep == EngineTier(
        multipv=4, min_time_ms=3000, min_depth=22, hard_cap_ms=8000, max_line_plies=10
    )


def test_classification_thresholds_match_spec_defaults() -> None:
    thresholds = Settings(_env_file=None).thresholds

    assert (thresholds.inaccuracy, thresholds.mistake, thresholds.blunder) == (0.10, 0.20, 0.30)


def test_env_vars_override_models_and_nested_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COACH_MODEL_CHAT", "claude-haiku-5-5")
    monkeypatch.setenv("THRESHOLDS__BLUNDER", "0.35")

    settings = Settings(_env_file=None)

    assert settings.coach_model_chat == "claude-haiku-5-5"
    assert settings.thresholds.blunder == 0.35
