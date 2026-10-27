"""Application settings. Every threshold and engine setting lives here (SPEC §5.3, §6.1)."""

from functools import lru_cache
from typing import Literal

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
    # The live engine panel (SPEC_V2 §5.5): 3 lines, runs until the 10 s cap on one position.
    # Its results are only shown, never posted to the backend.
    live: EngineTier = EngineTier(
        multipv=3, min_time_ms=10_000, min_depth=99, hard_cap_ms=10_000, max_line_plies=10
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


Effort = Literal["low", "medium", "high", "xhigh", "max"]


class CoachSettings(BaseModel):
    """Claude call settings (SPEC §7). Thinking is always on for current models and counts
    toward max_tokens, so these leave room for it."""

    synopsis_max_tokens: int = 8000
    synopsis_effort: Effort = "low"
    # The prompt asks for <= 300 words; past this ceiling the backend logs a warning.
    synopsis_max_words: int = 350
    # What the coach sees of each key moment's engine lines. The full lines stay in the stored
    # summary; the coach only needs enough to explain the idea (input tokens are most of the cost).
    coach_engine_lines: int = 2
    coach_line_plies: int = 6
    chat_max_tokens: int = 6000
    chat_effort: Effort = "medium"
    chat_max_messages: int = 30  # per game (PLAN Q27)
    chat_max_message_chars: int = 2000
    chat_max_tool_calls: int = 2  # analyze_position calls per user message (SPEC §8.3)
    # While the coach is writing (responses are validated before they're sent, PLAN Q22), the
    # SSE stream sends a keepalive comment this often so proxies don't drop the connection.
    keepalive_s: float = 10


class Limits(BaseModel):
    """Input size limits for user-submitted data."""

    max_pgn_chars: int = 100_000
    max_plies: int = 600
    # New single-game uploads per player per rolling 24 hours (PLAN_V2 §6 Q8). Onboarding games
    # don't count.
    max_games_per_day: int = 10
    max_playstyle_chars: int = 500


class AuthSettings(BaseModel):
    """Invite links and login sessions (SPEC_V2 §4.1)."""

    invite_ttl_days: int = 7
    session_ttl_days: int = 30
    cookie_name: str = "cochess_session"
    # Browsers treat http://localhost as secure, so this can stay on in development too. Turn it
    # off only to test over plain HTTP on another host.
    cookie_secure: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")

    anthropic_api_key: str = ""
    # Cost review (option B): Sonnet at low effort writes the synopsis, Haiku handles the chat.
    # Stronger models are a config change away (SPEC §11 v4: user-selectable coach strength).
    coach_model_synopsis: str = "claude-sonnet-5-5"
    coach_model_chat: str = "claude-haiku-5-5"
    database_url: str = "sqlite:///./cochess.db"
    # Where players open CoChess; invite links are built from it.
    public_base_url: str = "http://localhost:5173"

    auth: AuthSettings = AuthSettings()
    engine: EngineSettings = EngineSettings()
    thresholds: Thresholds = Thresholds()
    detectors: DetectorSettings = DetectorSettings()
    coach: CoachSettings = CoachSettings()
    limits: Limits = Limits()


@lru_cache
def get_settings() -> Settings:
    return Settings()
