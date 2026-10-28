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
    # The baseline report after onboarding (SPEC_V2 §10.4): asks for 400-600 words.
    baseline_max_tokens: int = 12000
    baseline_effort: Effort = "medium"
    baseline_max_words: int = 700
    baseline_moments_per_game: int = 3  # the player's worst moments in each game's summary
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


class MomentSettings(BaseModel):
    """Critical moments (SPEC_V2 §8): which moves become exercises, and how they're graded."""

    min_moments: int = 3  # top up with the biggest inaccuracies to reach this many
    max_moments: int = 6  # keep the biggest drops beyond this
    max_attempts: int = 2  # failed attempts before the answer is revealed
    # A candidate this close to the engine's best (winning-chances drop) counts as "best".
    best_margin: float = 0.02
    refutation_plies: int = 6  # how much of the line after a move the coach sees


class TendencySettings(BaseModel):
    """Tendency tracking (SPEC_V2 §9.2): mistake themes across games, recent games weighted most."""

    half_life_games: float = 10  # a game this many games back counts half as much as the latest
    top_n: int = 5  # tendencies the coach receives
    provisional_below_games: int = 5  # fewer analyzed games than this: tendencies are provisional
    trend_window_games: int = 5  # the last N games against the N before them
    trend_margin: float = 0.25  # occurrences per game: a smaller change is "steady"
    # Each fact counts with its severity's weight when ranking (PLAN_V2 §6 Q9). Game-level facts
    # are "concern" or "note"; notes (always-on summaries) never count.
    severity_weights: dict[str, float] = {
        "blunder": 3,
        "mistake": 2,
        "inaccuracy": 1,
        "concern": 2,
        "note": 0,
    }


class OnboardingSettings(BaseModel):
    """The onboarding assessment (SPEC_V2 §10)."""

    games_per_slot: int = 3  # White wins, White losses, Black wins, Black losses
    max_paste_games: int = 40  # games in one paste
    max_paste_chars: int = 600_000
    # Lichess's categories, by estimated duration = base + 40 x increment (seconds).
    bullet_below_s: int = 180
    blitz_below_s: int = 480
    rapid_below_s: int = 1500


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
    moments: MomentSettings = MomentSettings()
    tendencies: TendencySettings = TendencySettings()
    onboarding: OnboardingSettings = OnboardingSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
