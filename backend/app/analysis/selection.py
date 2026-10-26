"""Choosing which plies get a verify-tier search after the scan (SPEC §5.5)."""

from collections.abc import Sequence

from app.analysis.evals import Color, Evaluation, for_color, winning_chances
from app.analysis.pgn import ParsedGame
from app.config import Thresholds


def select_verify_plies(
    evals: Sequence[Evaluation], user_color: Color, thresholds: Thresholds
) -> list[int]:
    """Plies to verify, ascending.

    `evals[i]` is the evaluation of the position before ply i + 1; the last entry is the final
    position. Flags every user move whose winning-chances drop reaches the inaccuracy threshold,
    plus the largest swings by either side. If too many qualify, keeps the largest.
    """
    wc = [winning_chances(e) for e in evals]
    priority: dict[int, float] = {}

    for ply in range(1, len(evals)):
        if _mover(ply) != user_color:
            continue
        drop = for_color(wc[ply - 1] - wc[ply], user_color)
        if drop >= thresholds.inaccuracy:
            priority[ply] = drop

    swings = sorted(
        ((abs(wc[ply] - wc[ply - 1]), ply) for ply in range(1, len(evals))),
        key=lambda item: (-item[0], item[1]),
    )
    for swing, ply in swings[: thresholds.verify_top_swings]:
        priority[ply] = max(priority.get(ply, 0.0), swing)

    kept = sorted(priority, key=lambda ply: (-priority[ply], ply))[: thresholds.verify_max_plies]
    return sorted(kept)


def verify_fens(game: ParsedGame, plies: Sequence[int]) -> list[str]:
    """Positions before and after each ply, deduplicated, skipping a terminal final position."""
    fens_by_index = [p.fen_before for p in game.positions] + [game.final_fen]
    fens: list[str] = []
    for ply in plies:
        for fen in (fens_by_index[ply - 1], fens_by_index[ply]):
            if fen not in fens and not (fen == game.final_fen and game.final_is_terminal):
                fens.append(fen)
    return fens


def scan_fens(game: ParsedGame) -> list[str]:
    """Every position in the game, including the final one unless it's terminal."""
    fens = [p.fen_before for p in game.positions]
    if not game.final_is_terminal:
        fens.append(game.final_fen)
    return list(dict.fromkeys(fens))


def _mover(ply: int) -> Color:
    return "white" if ply % 2 == 1 else "black"
