"""PGN export (SPEC_V3 §5.2): NAGs, evaluations, moment notes, variations, and the round trip."""

import io

import chess
import chess.pgn

from app.analysis.evals import Evaluation
from app.analysis.pgn import parse_pgn
from app.analysis.pgn_export import ExportMoment, export_filename, export_pgn
from app.analysis.summary_models import MoveLabel
from app.analysis.variations import SavedVariation
from tests.pgn_fixtures import read_pgn

OPERA = parse_pgn(read_pgn("opera_game.pgn"), max_chars=100_000, max_plies=600)
CLOCKS = parse_pgn(read_pgn("annotated_clock_game.pgn"), max_chars=100_000, max_plies=600)


def _export(
    *,
    stored: str = OPERA.pgn,
    user_color: str = "white",
    evals: list[Evaluation] | None = None,
    labels: dict[int, MoveLabel | None] | None = None,
    moments: list[ExportMoment] | None = None,
    variations: list[SavedVariation] | None = None,
) -> chess.pgn.Game:
    text = export_pgn(
        stored,
        user_color="white" if user_color == "white" else "black",
        evals=evals,
        labels=labels or {},
        moments=moments or [],
        variations=variations or [],
    )
    game = chess.pgn.read_game(io.StringIO(text))
    assert game is not None
    return game


def _mainline_node(game: chess.pgn.Game, ply: int) -> chess.pgn.ChildNode:
    return list(game.mainline())[ply - 1]


def _lines(node: chess.pgn.GameNode, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Every path from the start to a leaf, as UCI."""
    if not node.variations:
        return {prefix}
    found: set[tuple[str, ...]] = set()
    for child in node.variations:
        found |= _lines(child, (*prefix, child.move.uci()))
    return found


def test_nags_mark_only_the_players_own_mistakes() -> None:
    labels: dict[int, MoveLabel | None] = {1: "blunder", 2: "mistake", 3: "inaccuracy", 5: None}
    game = _export(labels={**labels, 7: "missed_mate"})

    assert _mainline_node(game, 1).nags == {chess.pgn.NAG_BLUNDER}
    assert _mainline_node(game, 2).nags == set()  # Black's move: not the player's
    assert _mainline_node(game, 3).nags == {chess.pgn.NAG_DUBIOUS_MOVE}
    assert _mainline_node(game, 5).nags == set()
    assert _mainline_node(game, 7).nags == {chess.pgn.NAG_MISTAKE}


def test_playing_black_marks_blacks_moves() -> None:
    game = _export(user_color="black", labels={1: "blunder", 2: "mistake"})

    assert _mainline_node(game, 1).nags == set()
    assert _mainline_node(game, 2).nags == {chess.pgn.NAG_MISTAKE}


def test_every_mainline_move_carries_the_evaluation_after_it() -> None:
    evals = [Evaluation(cp=20 * i) for i in range(len(OPERA.positions))]
    evals.append(Evaluation(checkmated="black"))  # the final position: no eval comment
    evals[3] = Evaluation(mate=-3)

    game = _export(evals=evals)

    assert _mainline_node(game, 1).eval() == chess.engine.PovScore(chess.engine.Cp(20), chess.WHITE)
    assert _mainline_node(game, 3).eval() == chess.engine.PovScore(
        chess.engine.Mate(-3), chess.WHITE
    )
    assert _mainline_node(game, len(OPERA.positions)).eval() is None


def test_critical_moments_name_the_classification_and_best_move() -> None:
    game = _export(
        moments=[
            ExportMoment(ply=5, label="blunder", best_san="Nc3"),
            ExportMoment(ply=9, label="mistake", best_san=None),
        ]
    )

    assert _mainline_node(game, 5).comment == "Critical moment: a blunder. Best was Nc3."
    assert _mainline_node(game, 9).comment == "Critical moment: a mistake."


def test_headers_and_clocks_from_the_original_are_kept() -> None:
    game = _export(stored=CLOCKS.pgn, moments=[ExportMoment(ply=1, label="mistake", best_san="d4")])

    assert game.headers["TimeControl"] == "600+5"
    assert game.headers["White"] == "Player A"
    assert game.headers["Annotator"] == "CoChess"
    first = _mainline_node(game, 1)
    assert first.clock() == 600
    assert "Critical moment: a mistake." in first.comment


def test_variations_follow_the_game_move_and_keep_their_order() -> None:
    variations = [
        SavedVariation(start_path=["e2e4", "e7e5"], moves=["f1c4", "g8f6"]),
        SavedVariation(start_path=["e2e4", "e7e5"], moves=["b1c3"]),
        # Starts inside the first variation.
        SavedVariation(start_path=["e2e4", "e7e5", "f1c4"], moves=["f8c5"]),
        # Past the end of the game is allowed too; here, a line from the start.
        SavedVariation(start_path=[], moves=["d2d4", "d7d5"]),
    ]
    game = _export(variations=variations)

    after_e5 = _mainline_node(game, 2)
    assert [v.move.uci() for v in after_e5.variations] == ["g1f3", "f1c4", "b1c3"]
    assert after_e5.variations[0].is_mainline()
    assert [v.move.uci() for v in after_e5.variations[1].variations] == ["g8f6", "f8c5"]
    assert [v.move.uci() for v in game.variations] == ["e2e4", "d2d4"]


def test_round_trip_reimports_and_replays() -> None:
    variations = [
        SavedVariation(start_path=["e2e4", "e7e5"], moves=["f1c4", "g8f6", "d2d3"]),
        SavedVariation(start_path=[p.uci for p in OPERA.positions[:18]], moves=["c3d5"]),
    ]
    evals = [Evaluation(cp=10 * i) for i in range(len(OPERA.positions))]
    evals.append(Evaluation(checkmated="black"))
    text = export_pgn(
        OPERA.pgn,
        user_color="white",
        evals=evals,
        labels={9: "blunder"},
        moments=[ExportMoment(ply=9, label="blunder", best_san="Nc3")],
        variations=variations,
    )

    reimported = parse_pgn(text, max_chars=100_000, max_plies=600)
    assert [p.uci for p in reimported.positions] == [p.uci for p in OPERA.positions]
    assert reimported.final_fen == OPERA.final_fen
    for key, value in OPERA.headers.items():
        assert reimported.headers[key] == value

    game = chess.pgn.read_game(io.StringIO(text))
    assert game is not None and not game.errors
    lines = _lines(game)
    for variation in variations:
        path = (*variation.start_path, *variation.moves)
        assert any(line[: len(path)] == path for line in lines)


def test_filename_is_safe() -> None:
    assert export_filename(OPERA.headers) == "Paul_Morphy-vs-Duke_Karl_Count_Isouard.pgn"
    assert export_filename(CLOCKS.headers) == "Player_A-vs-Player_B-2026.01.01.pgn"
    assert export_filename({"White": "../x", "Black": "y"}) == "x-vs-y.pgn"
