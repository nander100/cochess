"""Theme-fact rows (SPEC_V2 §9.1): one per fact, with the move's phase, replaced on rebuild."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.detectors.types import ThemeFact
from app.db.models import Game, GameThemeFactRow, User
from app.db.tendencies import save_theme_facts
from tests.analysis.test_summary import opera_summary

PGN = "1. e4 e5 *"


def _game(session: Session, user_id: str | None) -> Game:
    game = Game(id="g", user_id=user_id, pgn=PGN, user_color="white", elo=1400, headers={})
    session.add(game)
    session.commit()
    return game


def _user(session: Session) -> User:
    user = User(name="Alex", name_key="alex")
    session.add(user)
    session.commit()
    return user


def _summary_with_facts():  # type: ignore[no-untyped-def]
    summary = opera_summary()
    facts = [
        ThemeFact(theme="hung_piece", ply=9, move_number=5, move_san="Qxf3", severity="blunder",
                  details={"piece": "queen"}),
        ThemeFact(theme="pawn_structure", ply=31, move_number=16, move_san="Qb8+",
                  severity="inaccuracy", details={"weakness": "doubled", "files": ["c"]}),
        ThemeFact(theme="time_trouble", severity="concern", details={}),
    ]  # fmt: skip
    return summary.model_copy(update={"theme_facts": facts})


def test_one_row_per_fact_with_the_moves_phase(db_session: Session) -> None:
    user = _user(db_session)
    game = _game(db_session, user.id)
    summary = _summary_with_facts()
    phases = {m.ply: m.phase for m in summary.move_list}

    save_theme_facts(db_session, game, summary)

    rows = list(db_session.scalars(select(GameThemeFactRow).order_by(GameThemeFactRow.id)))
    assert [(r.theme, r.subtype, r.ply, r.move_san, r.severity, r.phase) for r in rows] == [
        ("hung_piece", None, 9, "Qxf3", "blunder", phases[9]),
        ("pawn_structure", "doubled", 31, "Qb8+", "inaccuracy", phases[31]),
        ("time_trouble", None, None, None, "concern", None),
    ]
    assert phases[9] == "opening"
    assert {(r.user_id, r.game_id, r.user_color) for r in rows} == {(user.id, "g", "white")}


def test_rebuilding_replaces_the_rows(db_session: Session) -> None:
    game = _game(db_session, _user(db_session).id)

    save_theme_facts(db_session, game, _summary_with_facts())
    save_theme_facts(db_session, game, opera_summary())

    rows = list(db_session.scalars(select(GameThemeFactRow)))
    assert [r.theme for r in rows] == [f.theme for f in opera_summary().theme_facts]


def test_a_game_without_an_owner_gets_no_rows(db_session: Session) -> None:
    game = _game(db_session, None)

    save_theme_facts(db_session, game, _summary_with_facts())

    assert list(db_session.scalars(select(GameThemeFactRow))) == []
