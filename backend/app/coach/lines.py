"""The lines a coach reply can link to (SPEC_V3 §9.4), resolved from the data the coach was given:
`{{line:<position>.<line>|text}}` names a line; the moves always come from here, never from the
coach. `here` is the position the message is about; `km<N>` is the game summary's key moment N.
"""

from collections.abc import Sequence

import chess

from app.analysis.engine import EngineResult
from app.analysis.paths import ResolvedPath
from app.analysis.pgn import ParsedGame
from app.analysis.summary_models import GameSummary
from app.coach.markup import LineKind, ResolvedLine
from app.coach.payload import MomentPayload

ENGINE_REFS = tuple(f"engine{i}" for i in range(1, 5))


def san_to_uci(fen: str, sans: Sequence[str]) -> list[str]:
    """UCI for SAN moves played from `fen`, stopping at the first that doesn't parse. Move
    numbers ("14...Qxd4") are allowed."""
    board = chess.Board(fen)
    moves = []
    for san in sans:
        try:
            move = board.parse_san(san.split(".")[-1].strip())
        except ValueError:
            break
        moves.append(move.uci())
        board.push(move)
    return moves


def _line(start: Sequence[str], moves: Sequence[str], kind: LineKind, plies: int) -> ResolvedLine:
    return ResolvedLine(tuple(start), tuple(moves[:plies]), kind)


def engine_lines(
    prefix: str, start: Sequence[str], result: EngineResult | None, plies: int
) -> dict[str, ResolvedLine]:
    if result is None:
        return {}
    return {
        f"{prefix}.{ref}": _line(start, line.moves_uci, "engine", plies)
        for ref, line in zip(ENGINE_REFS, result.lines, strict=False)
    }


def key_moment_lines(game: ParsedGame, summary: GameSummary, plies: int) -> dict[str, ResolvedLine]:
    """km<N>.engine1-4 (from the position before the move), km<N>.refutation (the move, then
    what the engine expects after it) and km<N>.best (the engine's top line)."""
    lines: dict[str, ResolvedLine] = {}
    for number, moment in enumerate(summary.key_moments, start=1):
        if not 1 <= moment.ply <= len(game.positions):
            continue
        position = game.positions[moment.ply - 1]
        start = [p.uci for p in game.positions[: moment.ply - 1]]
        prefix = f"km{number}"
        for ref, summary_line in zip(ENGINE_REFS, moment.engine_lines, strict=False):
            moves = san_to_uci(position.fen_before, summary_line.moves_san)
            if moves:
                lines[f"{prefix}.{ref}"] = _line(start, moves, "engine", plies)
        if f"{prefix}.engine1" in lines:
            best = lines[f"{prefix}.engine1"]
            lines[f"{prefix}.best"] = ResolvedLine(best.start_path_uci, best.moves_uci, "best")
        after = chess.Board(position.fen_before)
        after.push_uci(position.uci)
        reply = san_to_uci(after.fen(), moment.line_after_san)
        lines[f"{prefix}.refutation"] = _line(start, [position.uci, *reply], "refutation", plies)
    return lines


def chat_lines(
    game: ParsedGame,
    summary: GameSummary,
    board: ResolvedPath,
    here: EngineResult | None,
    after_game_move: EngineResult | None,
    plies: int,
) -> dict[str, ResolvedLine]:
    """Chat and Explain: the engine lines from the board's position, the game's move from there
    followed by the engine's reply (`refutation`), the player's own line when they've left the
    game (`variation`), and every key moment's lines."""
    lines = key_moment_lines(game, summary, plies)
    lines |= engine_lines("here", board.path_uci, here, plies)
    if board.on_mainline and board.ply < len(game.positions):
        game_move = game.positions[board.ply].uci
        reply = after_game_move.lines[0].moves_uci if after_game_move is not None else []
        lines["here.refutation"] = _line(board.path_uci, [game_move, *reply], "refutation", plies)
    if not board.on_mainline and board.branch_ply is not None:
        branch = board.branch_ply - 1
        lines["here.variation"] = _line(
            board.path_uci[:branch], board.path_uci[branch:], "variation", plies
        )
    return lines


def moment_lines(
    start: Sequence[str],
    fen: str,
    game_uci: str,
    moment: MomentPayload,
    plies: int,
) -> tuple[dict[str, ResolvedLine], frozenset[str]]:
    """A critical moment's lines, from the payload (already scrubbed of the answer): the game's
    move and what follows (`refutation`), the player's try and its refutation (`candidate`),
    and, once revealed, the engine's lines and `best`. Before that, those are withheld: linking
    to them is a leak."""
    lines: dict[str, ResolvedLine] = {}
    after = chess.Board(fen)
    after.push_uci(game_uci)
    refutation = san_to_uci(after.fen(), moment.game_move.refutation_san)
    lines["here.refutation"] = _line(start, [game_uci, *refutation], "refutation", plies)
    if moment.candidate is not None:
        tried = san_to_uci(fen, [moment.candidate.san])
        if tried:
            played = chess.Board(fen)
            played.push_uci(tried[0])
            reply = san_to_uci(played.fen(), moment.candidate.refutation_san)
            lines["here.candidate"] = _line(start, [tried[0], *reply], "candidate", plies)
    if moment.best is None:
        return lines, frozenset({"here.best", *(f"here.{ref}" for ref in ENGINE_REFS)})
    for ref, summary_line in zip(ENGINE_REFS, moment.best.lines, strict=False):
        moves = san_to_uci(fen, summary_line.moves_san)
        if moves:
            lines[f"here.{ref}"] = _line(start, moves, "engine", plies)
            if ref == "engine1":
                lines["here.best"] = _line(start, moves, "best", plies)
    return lines, frozenset()
