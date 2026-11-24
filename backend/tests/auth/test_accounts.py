"""Owner actions on accounts (SPEC_V4 §4.3, §4.4): accept from the waitlist, pause and restore
access, set the owner role. Each one queues its email in the same transaction."""

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.accounts import AccountError, admit, restore, set_role, suspend
from app.auth.service import create_user, start_session
from app.cli import main
from app.config import Settings
from app.db.models import AuthSession, EmailOutboxRow, User
from app.db.session import make_engine
from tests.auth_helpers import log_in
from tests.databases import fresh_database_url, is_postgres

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def _waitlisted(session: Session, name: str = "Sam") -> User:
    user = create_user(session, name)
    user.email, user.status, user.waitlisted_at = f"{name.lower()}@example.com", "waitlisted", NOW
    session.commit()
    return user


def _emails(session: Session, user: User) -> list[tuple[str, dict[str, str]]]:
    rows = session.scalars(
        select(EmailOutboxRow).where(EmailOutboxRow.user_id == user.id).order_by(EmailOutboxRow.id)
    )
    return [(row.kind, row.details) for row in rows]


def test_accepting_a_waitlisted_player_makes_them_active_and_emails_them(
    db_session: Session,
) -> None:
    user = _waitlisted(db_session)

    admit(db_session, user, NOW)
    db_session.commit()

    assert (user.status, user.admitted_at) == ("active", NOW)
    assert _emails(db_session, user) == [("accepted", {})]


def test_only_a_waitlisted_player_can_be_accepted(db_session: Session) -> None:
    user = create_user(db_session, "Already")  # CLI-made players start active

    with pytest.raises(AccountError, match="not on the waitlist"):
        admit(db_session, user, NOW)


def test_pausing_access_ends_every_session_and_keeps_the_reason_private_by_default(
    db_session: Session, settings: Settings
) -> None:
    user = _waitlisted(db_session)
    admit(db_session, user, NOW)
    start_session(db_session, user, NOW, settings.auth)
    start_session(db_session, user, NOW, settings.auth)
    db_session.commit()

    suspend(db_session, user, NOW, reason="spam uploads")
    db_session.commit()

    assert user.status == "suspended"
    sessions = db_session.scalars(select(AuthSession).where(AuthSession.user_id == user.id))
    assert sessions.all() == []
    assert ("access_paused", {}) in _emails(db_session, user)


def test_the_reason_goes_in_the_email_only_when_the_owner_asks(db_session: Session) -> None:
    user = _waitlisted(db_session)
    admit(db_session, user, NOW)

    suspend(db_session, user, NOW, reason="Too many games at once", tell_reason=True)
    db_session.commit()

    paused = [details for kind, details in _emails(db_session, user) if kind == "access_paused"]
    assert paused == [{"note": " The reason given: Too many games at once"}]


def test_restoring_access_returns_an_accepted_player_to_active(db_session: Session) -> None:
    user = _waitlisted(db_session)
    admit(db_session, user, NOW)
    suspend(db_session, user, NOW, reason="check")

    restore(db_session, user, NOW)
    db_session.commit()

    assert user.status == "active"
    assert [kind for kind, _ in _emails(db_session, user)].count("access_restored") == 1


def test_restoring_someone_paused_while_waitlisted_puts_them_back_on_the_waitlist(
    db_session: Session,
) -> None:
    user = _waitlisted(db_session)
    suspend(db_session, user, NOW, reason="check")

    restore(db_session, user, NOW)
    db_session.commit()

    assert user.status == "waitlisted"
    assert "access_restored" not in [kind for kind, _ in _emails(db_session, user)]


def test_each_pause_and_restore_sends_its_own_email(db_session: Session) -> None:
    later = datetime(2026, 11, 25, tzinfo=UTC)
    user = _waitlisted(db_session)
    admit(db_session, user, NOW)
    suspend(db_session, user, NOW, reason="one")
    restore(db_session, user, NOW)
    suspend(db_session, user, later, reason="two")
    restore(db_session, user, later)
    db_session.commit()

    kinds = [kind for kind, _ in _emails(db_session, user)]
    assert (kinds.count("access_paused"), kinds.count("access_restored")) == (2, 2)
    with pytest.raises(AccountError, match="isn't paused"):
        restore(db_session, user, NOW)


def test_set_role_only_takes_known_roles(db_session: Session) -> None:
    user = create_user(db_session, "Owner2")

    set_role(user, "owner")

    assert user.role == "owner"
    with pytest.raises(AccountError, match="role"):
        set_role(user, "admin")


def test_a_paused_player_is_logged_out_of_the_app(app: FastAPI) -> None:
    client = log_in(app, "Paused")
    with app.state.session_factory() as session:
        user = session.scalars(select(User).where(User.name == "Paused")).one()
        suspend(session, user, NOW, reason="check")
        session.commit()

    assert client.get("/api/games").status_code == 401


@pytest.fixture
def cli_settings(tmp_path: Path) -> Settings:
    url = fresh_database_url() if is_postgres() else f"sqlite:///{tmp_path / 'cli.db'}"
    return Settings(_env_file=None, database_url=url, public_base_url="https://cochess.example/")


def _cli(settings: Settings, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    return main(list(argv), settings, out), out.getvalue()


def test_the_cli_accepts_pauses_and_restores_a_player_found_by_name_or_email(
    cli_settings: Settings,
) -> None:
    _cli(cli_settings, "create-user", "--name", "Sam")
    with sessionmaker(make_engine(cli_settings.database_url))() as session:
        user = session.scalars(select(User)).one()
        user.email, user.status = "sam@example.com", "waitlisted"
        session.commit()

    assert _cli(cli_settings, "admit", "--user", "SAM@example.com") == (
        0,
        'Accepted "Sam": they can sign in now (acceptance email queued).\n',
    )
    code, out = _cli(cli_settings, "suspend", "--user", "Sam", "--reason", "testing")
    assert code == 0 and out.startswith('Paused "Sam"')
    assert _cli(cli_settings, "restore", "--user", "Sam")[0] == 0
    assert _cli(cli_settings, "set-role", "--user", "Sam", "--role", "owner")[0] == 0
    assert _cli(cli_settings, "admit", "--user", "Sam")[0] == 1  # already active
    assert _cli(cli_settings, "admit", "--user", "nobody@example.com")[0] == 1


def test_the_cli_grants_and_removes_credits_with_a_note(cli_settings: Settings) -> None:
    from app.billing.ledger import balance

    _cli(cli_settings, "create-user", "--name", "Sam")  # created players get the trial too

    assert (
        _cli(cli_settings, "grant-credits", "--user", "Sam", "--credits", "20", "--note", "beta")[0]
        == 0
    )
    code, out = _cli(
        cli_settings, "grant-credits", "--user", "Sam", "--credits", "-5", "--note", "fix"
    )
    assert (code, out) == (0, 'Removed 5 credits for "Sam".\n')
    assert (
        _cli(cli_settings, "grant-credits", "--user", "Sam", "--credits", "1", "--note", " ")[0]
        == 1
    )
    with sessionmaker(make_engine(cli_settings.database_url))() as session:
        user = session.scalars(select(User)).one()
        assert balance(session, user.id).total == (50 + 20 - 5) * 10_000


def test_the_cli_turns_metering_off_and_on(cli_settings: Settings) -> None:
    _cli(cli_settings, "create-user", "--name", "Tester")

    assert _cli(cli_settings, "metering", "--user", "Tester", "--off")[1].endswith("(unmetered).\n")
    with sessionmaker(make_engine(cli_settings.database_url))() as session:
        assert session.scalars(select(User.unmetered)).one() is True
    _cli(cli_settings, "metering", "--user", "Tester", "--on")
    with sessionmaker(make_engine(cli_settings.database_url))() as session:
        assert session.scalars(select(User.unmetered)).one() is False


def test_grant_trials_covers_existing_players_once(cli_settings: Settings) -> None:
    from app.db.models import CreditLedgerRow

    _cli(cli_settings, "create-user", "--name", "New")  # gets the trial at creation
    with sessionmaker(make_engine(cli_settings.database_url))() as session:
        # A v3 player from before credits: active, no trial.
        session.add(User(name="Old", name_key="old"))
        session.commit()

    assert _cli(cli_settings, "grant-trials") == (0, "Gave the free trial to 1 player(s).\n")
    assert _cli(cli_settings, "grant-trials") == (0, "Gave the free trial to 0 player(s).\n")
    with sessionmaker(make_engine(cli_settings.database_url))() as session:
        trials = session.scalars(select(CreditLedgerRow).where(CreditLedgerRow.kind == "trial"))
        assert len(trials.all()) == 2


def test_price_usage_prices_old_calls_without_charging(cli_settings: Settings) -> None:
    from app.billing.ledger import balance
    from app.db.models import LlmUsageRow

    _cli(cli_settings, "create-user", "--name", "Old")
    with sessionmaker(make_engine(cli_settings.database_url))() as session:
        user = session.scalars(select(User)).one()
        session.add(
            LlmUsageRow(
                user_id=user.id, endpoint="chat", task="chat", model="claude-haiku-5-5",
                input_tokens=1000, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
            )
        )  # fmt: skip
        session.commit()

    assert _cli(cli_settings, "price-usage")[0] == 0
    with sessionmaker(make_engine(cli_settings.database_url))() as session:
        assert session.scalars(select(LlmUsageRow.cost_microusd)).one() == 100
        assert balance(session, session.scalars(select(User.id)).one()).total == 50 * 10_000
