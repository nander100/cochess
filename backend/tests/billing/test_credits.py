"""Pricing and the credit ledger (SPEC_V4 §5.1, §5.2, §14.3)."""

import logging
import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import create_user
from app.billing.ledger import (
    adjust_by_owner,
    balance,
    charge_usage,
    expire_allowance,
    grant_allowance,
    grant_trial,
    history,
)
from app.billing.pricing import cost_microusd
from app.coach.client import Usage
from app.config import PricingSettings, Settings
from app.db.models import CreditLedgerRow, User
from tests.databases import is_postgres

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
CREDIT = 10_000  # microdollars
USAGE = Usage(input_tokens=1000, output_tokens=500, cache_read_tokens=2000, cache_write_tokens=100)


def _player(session: Session, name: str = "Sam") -> User:
    return create_user(session, name)


# Pricing


def test_a_call_costs_its_tokens_at_the_models_prices_rounded_up() -> None:
    # 1000 x 0.10 + 500 x 0.50 + 2000 x 0.01 + 100 x 0.125 = 382.5 microdollars
    assert cost_microusd(PricingSettings(), "claude-haiku-5-5", USAGE) == 383


def test_sonnet_and_opus_cost_what_the_price_list_says() -> None:
    usage = Usage(
        input_tokens=1_000_000, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0
    )

    assert cost_microusd(PricingSettings(), "claude-sonnet-5-5", usage) == 2_000_000
    assert cost_microusd(PricingSettings(), "claude-opus-5-5", usage) == 4_000_000


def test_an_unknown_model_is_priced_at_the_highest_rates_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.billing"):
        cost = cost_microusd(PricingSettings(), "some-new-model", USAGE)

    assert cost == cost_microusd(PricingSettings(), "claude-opus-5-5", USAGE)
    assert "some-new-model" in caplog.text


def test_settings_refuse_a_coach_model_without_a_price() -> None:
    with pytest.raises(ValueError, match="no price"):
        Settings(_env_file=None, coach_model_chat="claude-unpriced")


# The ledger


def test_the_trial_is_given_once(db_session: Session) -> None:
    user = _player(db_session)
    settings = Settings(_env_file=None)

    grant_trial(db_session, user, NOW, settings.credits)
    grant_trial(db_session, user, NOW, settings.credits)
    db_session.commit()

    assert balance(db_session, user.id).total == 50 * CREDIT
    trials = db_session.scalars(select(CreditLedgerRow).where(CreditLedgerRow.kind == "trial"))
    assert len(trials.all()) == 1


def test_usage_spends_the_allowance_before_lasting_credit(db_session: Session) -> None:
    user = _player(db_session)
    adjust_by_owner(db_session, user, 5 * CREDIT, note="welcome", now=NOW)
    grant_allowance(db_session, user, 1 * CREDIT, "test-allowance-1", NOW + timedelta(days=30), NOW)

    charge_usage(db_session, user.id, 1, 15_000, NOW)
    db_session.commit()

    now = balance(db_session, user.id)
    assert (now.allowance, now.lasting) == (0, 4 * CREDIT + 5_000)
    usage = history(db_session, user.id)[0]
    assert (usage.kind, usage.delta_microusd, usage.bucket) == ("usage", -15_000, "split")


def test_a_call_can_take_the_balance_slightly_below_zero(db_session: Session) -> None:
    user = _player(db_session)
    adjust_by_owner(db_session, user, 1_000, note="tiny", now=NOW)

    charge_usage(db_session, user.id, 1, 3_000, NOW)
    db_session.commit()

    assert balance(db_session, user.id).total == -2_000


def test_each_usage_row_is_charged_once(db_session: Session) -> None:
    user = _player(db_session)
    adjust_by_owner(db_session, user, CREDIT, note="x", now=NOW)

    charge_usage(db_session, user.id, 7, 1_000, NOW)
    charge_usage(db_session, user.id, 7, 1_000, NOW)
    db_session.commit()

    assert balance(db_session, user.id).total == CREDIT - 1_000


def test_owner_grants_and_removals_need_a_note(db_session: Session) -> None:
    user = _player(db_session)

    adjust_by_owner(db_session, user, 3 * CREDIT, note="beta tester", now=NOW)
    adjust_by_owner(db_session, user, -1 * CREDIT, note="correction", now=NOW + timedelta(1))
    db_session.commit()

    assert balance(db_session, user.id).total == 2 * CREDIT
    assert [e.kind for e in history(db_session, user.id)] == ["owner_removal", "owner_grant"]
    with pytest.raises(ValueError, match="note"):
        adjust_by_owner(db_session, user, CREDIT, note="  ", now=NOW)


def test_unused_allowance_expires_and_lasting_credit_stays(db_session: Session) -> None:
    user = _player(db_session)
    adjust_by_owner(db_session, user, 2 * CREDIT, note="kept", now=NOW)
    grant_allowance(db_session, user, 3 * CREDIT, "period-1", NOW + timedelta(days=30), NOW)
    charge_usage(db_session, user.id, 1, CREDIT, NOW)

    expire_allowance(db_session, user, "period-1", NOW + timedelta(days=30))
    expire_allowance(db_session, user, "period-1", NOW + timedelta(days=30))  # once only
    db_session.commit()

    now = balance(db_session, user.id)
    assert (now.allowance, now.lasting) == (0, 2 * CREDIT)
    expiry = history(db_session, user.id)[0]
    assert (expiry.kind, expiry.delta_microusd) == ("expiry", -2 * CREDIT)


def test_a_player_with_no_entries_has_nothing(db_session: Session) -> None:
    user = _player(db_session)

    assert balance(db_session, user.id).total == 0
    assert history(db_session, user.id) == []


@pytest.mark.skipif(not is_postgres(), reason="row locks need Postgres")
def test_two_charges_at_once_both_count(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        user = _player(session)
        adjust_by_owner(session, user, 10 * CREDIT, note="start", now=NOW)
        session.commit()
        user_id = user.id

    barrier = threading.Barrier(8)

    def charge(row: int) -> None:
        with app.state.session_factory() as session:
            barrier.wait()
            charge_usage(session, user_id, row, CREDIT, NOW)
            session.commit()

    threads = [threading.Thread(target=charge, args=(row,)) for row in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with app.state.session_factory() as session:
        assert balance(session, user_id).total == 2 * CREDIT
