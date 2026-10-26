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


class EngineSettings(BaseModel):
    """Served to the browser by GET /api/engine-config, so the backend stays the one source."""

    max_threads: int = 4  # browser uses min(hardwareConcurrency - 1, max_threads)
    hash_mb: int = 64
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
    # A lost forced mate only counts if the mover's win% afterwards is below this; missing a
    # mate while still completely winning isn't a mistake worth coaching (M3 review).
    missed_mate_max_win_pct_after: float = 90
    verify_top_swings: int = 3
    verify_max_plies: int = 15
    key_moments_max: int = 8
    key_moment_swings: int = 3


class DetectorSettings(BaseModel):
    """Game phase (SPEC §6.2) and theme-detector thresholds (SPEC §6.4)."""

    opening_max_ply: int = 20
    endgame_max_non_pawn_material: int = 26
    min_material_gain: int = 2  # "wins material >= 2" (points: N=B=3, R=5, Q=9)
    hung_piece_plies: int = 3
    tactic_plies: int = 5
    king_check_plies: int = 3
    development_move: int = 10
    min_undeveloped_minors: int = 2
    castle_by_move: int = 12
    opening_wc_loss_for_concern: float = 0.15
    threw_win_from_pct: float = 70
    threw_win_to_pct: float = 55
    passive_king_center_distance: int = 3
    low_clock_fraction: float = 0.10
    low_clock_default_s: float = 30


class Limits(BaseModel):
    """Input size limits for user-submitted data."""

    max_pgn_chars: int = 100_000
    max_plies: int = 600
    max_playstyle_chars: int = 500


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")

    access_code: str = ""
    anthropic_api_key: str = ""
    coach_model_synopsis: str = "claude-opus-5-5"
    coach_model_chat: str = "claude-sonnet-5-5"
    database_url: str = "sqlite:///./cochess.db"

    engine: EngineSettings = EngineSettings()
    thresholds: Thresholds = Thresholds()
    detectors: DetectorSettings = DetectorSettings()
    limits: Limits = Limits()


@lru_cache
def get_settings() -> Settings:
    return Settings()
