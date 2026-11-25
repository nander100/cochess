"""The CLI's owner commands write the same audit rows as the dashboard, with no admin user
(SPEC_V4 §10.3: they stay in the CLI for when the web app is down), and `usage-report` prints
the overview."""

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.service import create_user
from app.cli import main
from app.config import Settings
from app.db.migrate import upgrade
from app.db.models import AdminActionRow, CreditLedgerRow, LlmUsageRow
from app.db.session import make_engine
from tests.databases import fresh_database_url, is_postgres


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    url = fresh_database_url() if is_postgres() else f"sqlite:///{tmp_path / 'cli.db'}"
    upgrade(make_engine(url))
    return Settings(_env_file=None, database_url=url)


def _session(settings: Settings) -> Session:
    return sessionmaker(make_engine(settings.database_url), expire_on_commit=False)()


def _run(settings: Settings, *argv: str) -> int:
    return main(list(argv), settings, io.StringIO())


def _audit(settings: Settings) -> list[tuple[str | None, str, dict[str, object]]]:
    with _session(settings) as session:
        rows = session.scalars(select(AdminActionRow).order_by(AdminActionRow.id))
        return [(r.admin_user_id, r.action, dict(r.details)) for r in rows]


def test_each_owner_command_writes_one_audit_row(settings: Settings) -> None:
    with _session(settings) as session:
        user = create_user(session, "Newcomer")
        user.status, user.email = "waitlisted", "new@example.com"
        session.commit()

    assert _run(settings, "admit", "--user", "new@example.com") == 0
    assert (
        _run(settings, "grant-credits", "--user", "Newcomer", "--credits", "5", "--note", "hi") == 0
    )
    assert _run(settings, "metering", "--user", "Newcomer", "--off") == 0
    assert _run(settings, "suspend", "--user", "Newcomer", "--reason", "spam") == 0
    assert _run(settings, "restore", "--user", "Newcomer") == 0
    assert _run(settings, "set-role", "--user", "Newcomer", "--role", "owner") == 0

    suspended = {"reason": "spam", "told_reason": False, "cancelled_subscription": False}
    assert _audit(settings) == [
        (None, "accept", {}),
        (None, "credits", {"credits": 5.0, "note": "hi"}),
        (None, "metering", {"unmetered": True}),
        (None, "suspend", suspended),
        (None, "restore", {"status": "active"}),
        (None, "set_role", {"from": "player", "to": "owner"}),
    ]
    with _session(settings) as session:
        query = select(CreditLedgerRow.source).where(CreditLedgerRow.kind == "owner_grant")
        sources = session.scalars(query).all()
    assert len(sources) == 1 and sources[0].startswith("admin_action:")


def test_a_refused_command_writes_no_audit_row(settings: Settings) -> None:
    with _session(settings) as session:
        create_user(session, "Active")

    assert _run(settings, "admit", "--user", "Active") == 1
    assert _run(settings, "metering", "--user", "Active", "--on") == 1  # already metered
    assert _run(settings, "grant-credits", "--user", "Active", "--credits", "0", "--note", "x") == 1
    assert _audit(settings) == []


def test_usage_report_prints_the_overview(settings: Settings) -> None:
    with _session(settings) as session:
        create_user(session, "Someone")
    out = io.StringIO()

    code = main(["usage-report", "--period", "all"], settings, out)

    assert code == 0
    text = out.getvalue()
    assert "Period: all" in text
    assert "Players: 1 (1 active); waitlist 0" in text
    assert "API cost $0.00" in text
    assert "Coach calls by task: none" in text


def test_spend_sums_the_last_hours_of_api_cost(settings: Settings) -> None:
    now = datetime.now(UTC)
    with _session(settings) as session:
        for hours_ago, cost in ((1, 12_500), (5, 7_500), (30, 999_000)):
            session.add(
                LlmUsageRow(
                    endpoint="chat", task="chat", model="m", input_tokens=1, output_tokens=1,
                    cache_read_tokens=0, cache_write_tokens=0, cost_microusd=cost,
                    created_at=now - timedelta(hours=hours_ago),
                )
            )  # fmt: skip
        session.commit()
    out = io.StringIO()

    assert main(["spend", "--hours", "24"], settings, out) == 0
    assert out.getvalue().strip() == "0.0200"
