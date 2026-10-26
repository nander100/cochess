"""pawn_structure (SPEC §6.4 #6): the user's inaccuracy-or-worse created a doubled, isolated or
backward pawn; plus a game-level summary of the user's structure at the end of the opening."""

import chess

from app.analysis.detectors.types import GameContext, MoveContext, ThemeFact, game_fact
from app.analysis.pawns import backward_pawns, doubled_files, isolated_files, passed_pawns


def detect(ctx: MoveContext) -> list[ThemeFact]:
    if not ctx.flagged:
        return []
    user, before, after = ctx.side, ctx.board_before, ctx.board_after
    created = {
        "doubled": doubled_files(after, user) - doubled_files(before, user),
        "isolated": isolated_files(after, user) - isolated_files(before, user),
        "backward": _files(backward_pawns(after, user)) - _files(backward_pawns(before, user)),
    }
    return [
        ctx.fact("pawn_structure", {"weakness": weakness, "files": sorted(files)})
        for weakness, files in created.items()
        if files
    ]


def detect_game(game: GameContext) -> list[ThemeFact]:
    board, move_number = _end_of_opening(game)
    user = chess.WHITE if game.user_color == "white" else chess.BLACK
    isolated = isolated_files(board, user)
    pawns = board.pieces(chess.PAWN, user)
    isolated_pawns = sum(chess.FILE_NAMES[chess.square_file(p)] in isolated for p in pawns)
    return [
        game_fact(
            "pawn_structure",
            "note",
            {
                "scope": "end_of_opening",
                "at_move": move_number,
                "doubled_files": sorted(doubled_files(board, user)),
                "isolated_pawns": isolated_pawns,
                "isolated_files": sorted(isolated),
                "passed_pawns": sorted(chess.square_name(s) for s in passed_pawns(board, user)),
            },
        )
    ]


def _end_of_opening(game: GameContext) -> tuple[chess.Board, int]:
    """The first position that isn't opening, or the final position (PLAN Q17)."""
    for move in game.moves:
        if move.phase != "opening":
            return move.board_before, move.move_number
    return game.final_board, game.moves[-1].move_number


def _files(squares: frozenset[chess.Square]) -> frozenset[str]:
    return frozenset(chess.FILE_NAMES[chess.square_file(s)] for s in squares)
