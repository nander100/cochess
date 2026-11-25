"""The overview's numbers (SPEC_V4 §10.1) on hand-built rows: users by status, paid vs unpaid,
activity, and money, including refunds reported as running totals."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.admin.overview import overview, period_start
from app.billing.ledger import adjust_by_owner, charge_usage, grant_top_up, grant_trial
from app.config import CreditSettings
from app.db.models import User
from tests.admin.helpers import CREDIT, NOW, admin_app, billing_event, player, usage

DAY = timedelta(days=1)


@pytest.fixture
def app() -> FastAPI:
    return admin_app()


def _get(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    assert user is not None
    return user


def test_period_starts() -> None:
    assert period_start("7d", NOW) == NOW - 7 * DAY
    assert period_start("30d", NOW) == NOW - 30 * DAY
    assert period_start("month", NOW) == datetime(2026, 11, 1, tzinfo=UTC)
    assert period_start("all", NOW) is None


def test_users_by_status_and_the_oldest_wait(app: FastAPI) -> None:
    player(app, "Early", status="waitlisted", waitlisted_at=NOW - 9 * DAY)
    player(app, "Late", status="waitlisted", waitlisted_at=NOW - DAY)
    player(app, "Paused", status="suspended")
    player(app, "Playing")
    player(app, "Gone", status="deleted")

    with app.state.session_factory() as session:
        users = overview(session, "30d", NOW).users

    assert users.total == 4
    assert users.by_status == {"waitlisted": 2, "suspended": 1, "active": 1}
    assert users.waitlist == 2
    assert users.oldest_wait_since == NOW - 9 * DAY


def test_paid_and_unpaid_players(app: FastAPI) -> None:
    ids = {n: player(app, n) for n in ("Sub", "Late", "Trial", "Spent", "Friend", "Buyer")}
    credits = CreditSettings()
    with app.state.session_factory() as session:
        _get(session, ids["Sub"]).subscription_status = "active"
        _get(session, ids["Late"]).subscription_status = "past_due"
        _get(session, ids["Friend"]).unmetered = True
        for name in ("Trial", "Spent", "Friend"):
            grant_trial(session, _get(session, ids[name]), NOW, credits)
        charge_usage(session, ids["Spent"], 1, 60 * CREDIT, NOW)
        grant_top_up(session, _get(session, ids["Buyer"]), 150 * CREDIT, "stripe:pi_1", NOW)
        billing_event(session, "e1", "customer.subscription.deleted", None, NOW - DAY,
                      user_id=ids["Late"])  # fmt: skip
        billing_event(session, "e2", "customer.subscription.deleted", None, NOW - 40 * DAY,
                      user_id=ids["Sub"])  # fmt: skip
        session.commit()

        plans = overview(session, "30d", NOW).plans

    assert plans.subscribers == 1
    assert plans.past_due == 1
    assert plans.cancelled_this_month == 1  # the one 40 days ago was last month
    assert plans.trial_with_credits == 1  # Trial; Friend is unmetered, Buyer paid
    assert plans.trial_without_credits == 3  # Spent (below zero), Sub and Late (no ledger)
    assert plans.zero_credits == 3  # Spent, Sub, Late; never the unmetered friend


def test_activity_over_7_and_30_days(app: FastAPI) -> None:
    new = player(app, "New", created_at=NOW - 2 * DAY)
    player(app, "Older", created_at=NOW - 20 * DAY)
    player(app, "Ancient", created_at=NOW - 90 * DAY)
    with app.state.session_factory() as session:
        _get(session, new).last_active_at = NOW - DAY
        usage(session, new, 100, NOW - DAY)
        usage(session, new, 100, NOW - 10 * DAY)
        session.commit()

        week, month = overview(session, "30d", NOW).activity

    assert (week.days, week.sign_ups, week.active_players, week.coach_calls) == (7, 1, 1, 1)
    assert (month.days, month.sign_ups, month.coach_calls) == (30, 2, 2)


def test_money_counts_payments_refunds_and_api_cost(app: FastAPI) -> None:
    payer = player(app, "Payer")
    with app.state.session_factory() as session:
        billing_event(session, "sub", "invoice.paid", 1000, NOW - DAY, object_id="in_1")
        billing_event(session, "top", "checkout.session.completed", 500, NOW - 2 * DAY,
                      object_id="pi_1")  # fmt: skip
        # A subscription's checkout isn't money in (its invoice is); a payment we received but
        # couldn't match to a player still is; one from before the period isn't in it.
        billing_event(session, "subcs", "checkout.session.completed", 1000, NOW - DAY,
                      outcome="ignored")  # fmt: skip
        billing_event(session, "lost", "invoice.paid", 1000, NOW - DAY, outcome="unmatched")
        billing_event(session, "old", "invoice.paid", 1000, NOW - 60 * DAY)
        # Two partial refunds of pi_1, each reporting the running total: 200 then 300 cents.
        billing_event(session, "r1", "charge.refunded", -200, NOW - 2 * DAY, object_id="pi_1")
        billing_event(session, "r2", "charge.refunded", -300, NOW - DAY, object_id="pi_1")
        usage(session, payer, 7_000, NOW - DAY, tokens=(100, 300, 100))
        usage(session, payer, 3_000, NOW - DAY, tokens=(500, 0, 0))
        usage(session, None, 1_000, NOW - 2 * DAY)
        session.commit()

        money = overview(session, "7d", NOW).money
        everything = overview(session, "all", NOW).money

    assert money.revenue_microusd == (1000 + 500 + 1000 - 300) * 100 * 100
    assert money.refunds_microusd == 300 * 100 * 100
    assert money.api_cost_microusd == 11_000
    assert money.difference_microusd == money.revenue_microusd - 11_000
    assert money.coached_players == 1  # the call with no player isn't anyone's
    assert money.cost_per_player_microusd == 11_000
    assert money.cache_hit_rate == pytest.approx(300 / 1_100)
    assert everything.revenue_microusd == money.revenue_microusd + 1000 * 100 * 100


def test_a_refund_that_continues_an_earlier_one_counts_only_the_difference(
    app: FastAPI,
) -> None:
    with app.state.session_factory() as session:
        billing_event(session, "r1", "charge.refunded", -200, NOW - 20 * DAY, object_id="pi_1")
        billing_event(session, "r2", "charge.refunded", -500, NOW - DAY, object_id="pi_1")
        billing_event(session, "r3", "charge.refunded", -100, NOW - DAY, object_id="pi_2")
        session.commit()

        week = overview(session, "7d", NOW).money

    assert week.refunds_microusd == (300 + 100) * 100 * 100


def test_credits_granted_and_spent(app: FastAPI) -> None:
    user_id = player(app, "Player")
    with app.state.session_factory() as session:
        user = _get(session, user_id)
        grant_trial(session, user, NOW - DAY, CreditSettings())
        adjust_by_owner(session, user, 10 * CREDIT, note="gift", now=NOW - DAY)
        adjust_by_owner(session, user, -3 * CREDIT, note="oops", now=NOW - DAY)
        charge_usage(session, user_id, 1, 4 * CREDIT, NOW - DAY)
        session.commit()

        money = overview(session, "7d", NOW).money

    assert money.credits_granted_microusd == 60 * CREDIT  # removals aren't grants
    assert money.credits_spent_microusd == 4 * CREDIT


def test_the_series_is_daily_and_monthly_for_all_time(app: FastAPI) -> None:
    user_id = player(app, "Player")
    with app.state.session_factory() as session:
        billing_event(session, "a", "invoice.paid", 1000, datetime(2026, 11, 20, 9, tzinfo=UTC))
        usage(session, user_id, 5_000, datetime(2026, 11, 20, 23, 30, tzinfo=UTC))
        usage(session, user_id, 2_000, datetime(2026, 10, 3, tzinfo=UTC))
        session.commit()

        daily = overview(session, "30d", NOW).series
        monthly = overview(session, "all", NOW).series

    assert [(d.day, d.revenue_microusd, d.api_cost_microusd) for d in daily] == [
        (date(2026, 11, 20), 1000 * 100 * 100, 5_000)
    ]
    assert [(d.day, d.api_cost_microusd) for d in monthly] == [
        (date(2026, 10, 1), 2_000),
        (date(2026, 11, 1), 5_000),
    ]


def test_coach_calls_by_task_in_the_period(app: FastAPI) -> None:
    user_id = player(app, "Player")
    with app.state.session_factory() as session:
        for task, age in (("chat", 1), ("chat", 2), ("synopsis", 3), ("synopsis", 50)):
            usage(session, user_id, 100, NOW - age * DAY, task=task)
        session.commit()

        assert overview(session, "7d", NOW).calls_by_task == {"chat": 2, "synopsis": 1}
        assert overview(session, "all", NOW).calls_by_task == {"chat": 2, "synopsis": 2}
