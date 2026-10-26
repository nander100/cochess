"""time_trouble (SPEC §6.4 #8, game-level): only with %clk. Low clock = <= 10% of the base time
from the TimeControl header, or <= 30 s without one."""

import re

from app.analysis.detectors.types import GameContext, ThemeFact, game_fact

_TIME_CONTROL = re.compile(r"^(\d+)(?:\+\d+)?$")


def base_time_s(time_control: str | None) -> int | None:
    """Base seconds from "600" or "600+5"; None for "-", "?", correspondence ("1/259200")."""
    match = _TIME_CONTROL.match((time_control or "").strip())
    return int(match.group(1)) if match else None


def detect(game: GameContext) -> list[ThemeFact]:
    moves = game.user_moves()
    if not any(m.clock_s is not None for m in moves):
        return []
    settings = game.settings
    base = base_time_s(game.headers.get("TimeControl"))
    threshold = base * settings.low_clock_fraction if base else settings.low_clock_default_s

    low_plies = {m.ply for m in moves if m.clock_s is not None and m.clock_s <= threshold}
    bad = [m for m in moves if m.classification in ("mistake", "blunder")]
    bad_low = [m for m in bad if m.ply in low_plies]
    first_low = next((m.move_number for m in moves if m.ply in low_plies), None)
    return [
        game_fact(
            "time_trouble",
            "concern" if bad_low else "note",
            {
                "base_time_s": base,
                "low_clock_threshold_s": round(threshold, 1),
                "low_clock_from_move": first_low,
                "user_moves": len(moves),
                "moves_in_low_clock": len(low_plies),
                "mistakes_and_blunders": len(bad),
                "mistakes_and_blunders_in_low_clock": len(bad_low),
                "share_in_low_clock_pct": round(100 * len(bad_low) / len(bad)) if bad else 0,
            },
        )
    ]
