"""The baseline report's per-game summary (SPEC_V2 §10.4)."""

from datetime import UTC, datetime

from app.coach.baseline import _game, opening_groups
from app.config import Settings
from app.db.models import Game
from tests.analysis.test_summary import opera_summary

SETTINGS = Settings(_env_file=None)


def _opera_game() -> Game:
    return Game(id="g", user_color="white", user_result="win", elo=1350, headers={}, pgn="",
                played_at=datetime(2026, 10, 1, tzinfo=UTC))  # fmt: skip


def test_each_game_is_summarized_compactly() -> None:
    # White's 6th move (ply 11) drops from 0.0 to -3.0: the player's blunder.
    summary = opera_summary({ply: -300 for ply in range(12, 34)})

    game = _game(4, _opera_game(), summary, SETTINGS)

    assert (game.number, game.date, game.color, game.result) == (4, "2026-10-01", "white", "win")
    assert game.opponent == "Duke Karl / Count Isouard"
    assert game.opening_moves == "1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3"
    assert game.counts.blunders == 1
    # Only the player's own labeled moments, with lines trimmed for the coach.
    assert [(m.ply, m.move_san, m.classification) for m in game.key_moments] == [
        (11, "Bc4", "blunder")
    ]
    assert all(len(line.moves_san) <= 6 for m in game.key_moments for line in m.engine_lines)


def test_at_most_the_three_worst_moments_per_game() -> None:
    summary = opera_summary({ply: -300 for ply in range(12, 34)})
    moments = [
        summary.key_moments[0].model_copy(update={"ply": ply, "classification": label})
        for ply, label in ((3, "inaccuracy"), (5, "mistake"), (7, "inaccuracy"), (9, "blunder"))
    ]

    game = _game(1, _opera_game(), summary.model_copy(update={"key_moments": moments}), SETTINGS)

    assert [(m.ply, m.classification) for m in game.key_moments] == [
        (3, "inaccuracy"),
        (5, "mistake"),
        (9, "blunder"),
    ]


def test_openings_are_counted_by_the_backend() -> None:
    summary = opera_summary()
    base = _game(1, _opera_game(), summary, SETTINGS)
    games = [
        base.model_copy(update={"opening_moves": "1. d4 d5 2. Bf4", "result": "win",
                                "opening_accuracy": 90.0, "opponent": "A"}),
        base.model_copy(update={"opening_moves": "1. d4 Nf6 2. Bf4", "result": "loss",
                                "opening_accuracy": 70.0, "opponent": "B"}),
        base.model_copy(update={"opening_moves": "1. e4 e5", "result": "loss",
                                "opening_accuracy": None, "opponent": "C"}),
        base.model_copy(update={"color": "black", "opening_moves": "1. e4 c6 2. d4 d5",
                                "result": "win", "opening_accuracy": 60.0, "opponent": "D"}),
        base.model_copy(update={"color": "black", "opening_moves": "1. e4 c6 2. Nf3 d5",
                                "result": "loss", "opening_accuracy": 50.0, "opponent": "E"}),
    ]  # fmt: skip

    groups = opening_groups(games)

    assert [(g.color, g.start, g.games, g.wins, g.losses, g.opening_accuracy, g.opponents)
            for g in groups] == [
        ("white", "1. d4", 2, 1, 1, 80.0, ["A", "B"]),
        ("white", "1. e4", 1, 0, 1, None, ["C"]),
        ("black", "1. e4 c6", 2, 1, 1, 55.0, ["D", "E"]),
    ]  # fmt: skip
