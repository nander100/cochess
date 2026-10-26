import json
from pathlib import Path

import pytest

from app.analysis.engine import EngineResult
from app.analysis.pgn import parse_pgn
from app.analysis.selection import scan_fens
from app.analysis.summary import build_summary
from app.analysis.summary_models import GameSummary, UserInfo
from app.config import Settings
from tests.engine_fakes import fake_result
from tests.pgn_fixtures import read_pgn

SETTINGS = Settings(_env_file=None)
ENGINE_FIXTURES = sorted((Path(__file__).parent.parent / "fixtures" / "engine").glob("*.json"))
WHITE = UserInfo(color="white", elo=1350, playstyle="attacking")


def opera_summary(cps_by_ply: dict[int, int] | None = None) -> GameSummary:
    """The Opera Game with flat evals, except chosen positions (`ply` = position before it)."""
    game = parse_pgn(read_pgn("opera_game.pgn"), max_chars=100_000, max_plies=600)
    fens = [p.fen_before for p in game.positions]
    cps = {fen: (cps_by_ply or {}).get(i + 1, 0) for i, fen in enumerate(fens)}
    results = [
        EngineResult.model_validate(fake_result(fen, "verify", cp=cps[fen], lines=2, plies=4))
        for fen in scan_fens(game)
    ]
    return build_summary(game, results, WHITE, SETTINGS)


def test_game_and_user_info_come_from_the_headers_and_profile() -> None:
    summary = opera_summary()

    assert summary.game.model_dump() == {
        "white": "Paul Morphy",
        "black": "Duke Karl / Count Isouard",
        "result": "1-0",
        "time_control": None,
        "opening": "Philidor Defense",
        "num_moves": 17,
    }
    assert summary.user == WHITE


def test_eval_curve_and_move_list_cover_every_ply() -> None:
    summary = opera_summary()

    assert len(summary.eval_curve) == len(summary.move_list) == 33
    assert summary.eval_curve[-1].eval == "+M0"  # 17. Rd8# is scored from the board
    assert summary.move_list[0].model_dump() == {
        "ply": 1,
        "move_number": 1,
        "side": "white",
        "san": "e4",
        "eval_after": "0.0",
        "classification": None,
    }


def test_a_user_blunder_is_counted_and_becomes_a_key_moment() -> None:
    # White's 6th move (ply 11) drops from 0.0 to -3.0 and stays there.
    summary = opera_summary({ply: -300 for ply in range(12, 34)})

    assert summary.counts.model_dump() == {
        "inaccuracies": 0,
        "mistakes": 0,
        "blunders": 1,
        "missed_mates": 0,
    }
    moment = next(m for m in summary.key_moments if m.ply == 11)
    assert (moment.move_san, moment.classification, moment.eval_before, moment.eval_after) == (
        "Bc4",
        "blunder",
        "0.0",
        "-3.0",
    )
    assert moment.best_move_san == moment.engine_lines[0].moves_san[0]
    assert [line.rank for line in moment.engine_lines] == [1, 2]
    assert len(moment.line_after_san) == 4  # the engine's continuation after 6. Bc4
    assert summary.move_list[10].classification == "blunder"
    assert summary.accuracy.user is not None and summary.accuracy.user < 100


def test_phase_breakdown_has_every_phase() -> None:
    summary = opera_summary()

    assert set(summary.phase_breakdown) == {"opening", "middlegame", "endgame"}
    assert summary.phase_breakdown["opening"].moves == 10
    assert summary.phase_breakdown["opening"].accuracy == 100.0


def test_summary_round_trips_through_json() -> None:
    summary = opera_summary({ply: -300 for ply in range(12, 34)})

    assert GameSummary.model_validate_json(summary.model_dump_json()) == summary


@pytest.mark.parametrize("path", ENGINE_FIXTURES, ids=lambda p: p.stem)
def test_owner_games_build_consistent_summaries(path: Path) -> None:
    engine = json.loads(path.read_text())
    pgn = next((path.parent.parent / "pgn" / "user").glob(f"{path.stem}.*")).read_text()
    game = parse_pgn(pgn, max_chars=100_000, max_plies=600)
    results = [EngineResult.model_validate(r) for r in engine["scan"] + engine["verify"]]
    user = UserInfo(color=engine["user_color"], elo=950, playstyle=None)

    summary = build_summary(game, results, user, SETTINGS)

    assert len(summary.move_list) == len(game.positions)
    assert len(summary.key_moments) <= SETTINGS.thresholds.key_moments_max
    for moment in summary.key_moments:
        assert moment.engine_lines, f"key moment at ply {moment.ply} has no engine lines"
        assert moment.best_move_san == moment.engine_lines[0].moves_san[0]
    for value in (summary.accuracy.user, summary.accuracy.opponent):
        assert value is not None and 0 <= value <= 100
    user_facts = [f for f in summary.theme_facts if f.ply is not None]
    assert all(summary.move_list[f.ply - 1].side == user.color for f in user_facts)
