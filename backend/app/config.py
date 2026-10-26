"""Application settings. Every threshold and engine setting lives here (SPEC §5.3, §6.1)."""

from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineTier(BaseModel):
    """One engine tier: stop once min time AND min depth are reached, or at the hard cap."""

    multipv: int
    min_time_ms: int
    min_depth: int
    hard_cap_ms: int
    max_line_plies: int


class EngineTiers(BaseModel):
    scan: EngineTier = EngineTier(
        multipv=1, min_time_ms=250, min_depth=12, hard_cap_ms=1000, max_line_plies=1
    )
    verify: EngineTier = EngineTier(
        multipv=4, min_time_ms=1500, min_depth=18, hard_cap_ms=3000, max_line_plies=10
    )
    deep: EngineTier = EngineTier(
        multipv=4, min_time_ms=3000, min_depth=22, hard_cap_ms=8000, max_line_plies=10
    )


class Thresholds(BaseModel):
    """Winning-chance drop thresholds (wc scale, -1..1) and verify-selection limits."""

    inaccuracy: float = 0.10
    mistake: float = 0.20
    blunder: float = 0.30
    verify_top_swings: int = 3
    verify_max_plies: int = 15


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")

    access_code: str = ""
    anthropic_api_key: str = ""
    coach_model_synopsis: str = "claude-opus-5-5"
    coach_model_chat: str = "claude-sonnet-5-5"
    database_url: str = "sqlite:///./cochess.db"

    engine: EngineTiers = EngineTiers()
    thresholds: Thresholds = Thresholds()


@lru_cache
def get_settings() -> Settings:
    return Settings()
