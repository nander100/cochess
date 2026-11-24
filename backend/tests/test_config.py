import pytest

from app.config import EngineTier, Settings


def test_engine_tiers_match_spec_defaults() -> None:
    settings = Settings(_env_file=None)

    # SPEC_V4 §8 (M3): stop at depth, no minimum time; scan and verify on a pool of 4 engines.
    assert settings.engine.scan == EngineTier(
        multipv=1, min_time_ms=0, min_depth=16, hard_cap_ms=1000, max_line_plies=1
    )
    assert settings.engine.verify == EngineTier(
        multipv=4, min_time_ms=0, min_depth=18, hard_cap_ms=3000, max_line_plies=10
    )
    assert (settings.engine.pool_size, settings.engine.pool_hash_mb) == (4, 16)
    assert settings.engine.deep == EngineTier(
        multipv=4, min_time_ms=3000, min_depth=22, hard_cap_ms=8000, max_line_plies=10
    )


def test_classification_thresholds_match_spec_defaults() -> None:
    thresholds = Settings(_env_file=None).thresholds

    assert (thresholds.inaccuracy, thresholds.mistake, thresholds.blunder) == (0.10, 0.20, 0.30)


def test_env_vars_override_models_and_nested_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COACH_MODEL_CHAT", "claude-sonnet-5-5")
    monkeypatch.setenv("THRESHOLDS__BLUNDER", "0.35")

    settings = Settings(_env_file=None)

    assert settings.coach_model_chat == "claude-sonnet-5-5"
    assert settings.thresholds.blunder == 0.35
