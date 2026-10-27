"""Engine results for single positions: the check on what the browser sends with a chat or
Explain message, and storing and finding them by position."""

import pytest
from sqlalchemy.orm import Session

from app.analysis.engine import EngineResult, EngineResultError, check_for_position
from app.config import EngineSettings
from app.db.engine_results import load_position_result, save_position_result, save_results
from app.db.models import Game
from tests.engine_fakes import fake_result

AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
TIERS = {"verify": EngineSettings().verify, "deep": EngineSettings().deep}


def result(fen: str, tier: str, **options: int) -> EngineResult:
    return EngineResult.model_validate(fake_result(fen, tier, **options))


def test_a_result_for_the_board_position_is_accepted_and_trimmed() -> None:
    checked = check_for_position(
        result(AFTER_E4, "verify", lines=4, plies=12), fen=AFTER_E4, tier_configs=TIERS
    )

    assert checked.fen == AFTER_E4
    assert {len(line.moves_uci) for line in checked.lines} == {10}  # the verify tier keeps 10


def test_move_counters_may_differ_but_the_stored_fen_is_the_backends() -> None:
    moved = result(AFTER_E4.replace(" 0 1", " 3 7"), "verify")

    assert check_for_position(moved, fen=AFTER_E4, tier_configs=TIERS).fen == AFTER_E4


def test_a_result_for_another_position_is_refused() -> None:
    other = "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1"

    with pytest.raises(EngineResultError, match="different position"):
        check_for_position(result(other, "verify"), fen=AFTER_E4, tier_configs=TIERS)


def test_a_scan_result_is_not_enough() -> None:
    with pytest.raises(EngineResultError, match="verify or deep"):
        check_for_position(result(AFTER_E4, "scan"), fen=AFTER_E4, tier_configs=TIERS)


def test_an_illegal_line_is_refused() -> None:
    good = result(AFTER_E4, "verify")
    bad = good.model_copy(
        update={"lines": [good.lines[0].model_copy(update={"moves_uci": ["e2e4"]})]}
    )

    with pytest.raises(EngineResultError, match="illegal move"):
        check_for_position(bad, fen=AFTER_E4, tier_configs=TIERS)


@pytest.fixture
def game_id(db_session: Session) -> str:
    game = Game(pgn="1. e4 *", user_color="white", elo=1400, headers={})
    db_session.add(game)
    db_session.commit()
    return game.id


def _depth(result: EngineResult | None) -> int | None:
    return None if result is None else result.depth


def test_position_results_are_found_without_move_counters(
    db_session: Session, game_id: str
) -> None:
    save_results(db_session, game_id, [result(AFTER_E4, "verify")])

    found = load_position_result(db_session, game_id, AFTER_E4.replace(" 0 1", " 5 9"))

    assert found is not None and found.fen == AFTER_E4


def test_deep_beats_verify_and_scan_is_ignored(db_session: Session, game_id: str) -> None:
    save_results(db_session, game_id, [result(AFTER_E4, "scan")])
    assert load_position_result(db_session, game_id, AFTER_E4) is None
    save_results(db_session, game_id, [result(AFTER_E4, "verify")])
    save_results(db_session, game_id, [result(AFTER_E4, "deep")])

    found = load_position_result(db_session, game_id, AFTER_E4)

    assert found is not None and found.tier == "deep"


def test_a_chat_result_never_replaces_the_games_own(db_session: Session, game_id: str) -> None:
    game_result = result(AFTER_E4, "verify", depth=20)
    save_results(db_session, game_id, [game_result])

    save_position_result(db_session, game_id, result(AFTER_E4, "verify", depth=3))

    assert _depth(load_position_result(db_session, game_id, AFTER_E4)) == 20


def test_a_chat_result_is_stored_for_a_new_position(db_session: Session, game_id: str) -> None:
    save_position_result(db_session, game_id, result(AFTER_E4, "verify", depth=17))

    assert _depth(load_position_result(db_session, game_id, AFTER_E4)) == 17
