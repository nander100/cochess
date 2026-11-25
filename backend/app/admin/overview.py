"""The owner dashboard's overview numbers (SPEC_V4 §10.1). Counts and money only: nothing here reads
a game's moves or a chat. Money is in microdollars (revenue converted from cents), days are UTC."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import ColumnElement, SQLColumnExpression, distinct, exists, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    BillingEventRow,
    CreditBalanceRow,
    CreditLedgerRow,
    Game,
    LlmUsageRow,
    User,
)

Period = Literal["7d", "30d", "month", "all"]
MICROUSD_PER_CENT = 10_000
SUBSCRIBED = ("active", "trialing")
PAST_DUE = ("past_due", "incomplete", "unpaid")
PAYMENTS = ("checkout.session.completed", "invoice.paid")  # applied: money in
GRANTS = ("trial", "allowance", "top_up", "owner_grant")
COUNTED = ("applied", "unmatched")  # an unmatched payment is still money received


class UserCounts(BaseModel):
    total: int
    by_status: dict[str, int]
    waitlist: int
    oldest_wait_since: datetime | None


class PlanCounts(BaseModel):
    subscribers: int
    past_due: int
    cancelled_this_month: int
    trial_with_credits: int
    trial_without_credits: int
    zero_credits: int


class Activity(BaseModel):
    days: int
    sign_ups: int
    acceptances: int
    active_players: int
    games_added: int
    coach_calls: int


class Money(BaseModel):
    revenue_microusd: int  # as charged, including any tax, before Stripe fees; net of refunds
    refunds_microusd: int
    api_cost_microusd: int
    difference_microusd: int
    coached_players: int
    coached_games: int
    cost_per_player_microusd: int | None
    cost_per_game_microusd: int | None
    credits_granted_microusd: int
    credits_spent_microusd: int
    cache_hit_rate: float | None  # cache reads / every input token


class DayMoney(BaseModel):
    day: date  # the first day of the month for "all"
    revenue_microusd: int
    api_cost_microusd: int


class Overview(BaseModel):
    period: Period
    since: datetime | None
    users: UserCounts
    plans: PlanCounts
    activity: list[Activity]  # the last 7 and 30 days
    calls_by_task: dict[str, int]  # in the period
    money: Money
    series: list[DayMoney]


def period_start(period: Period, now: datetime) -> datetime | None:
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


def overview(session: Session, period: Period, now: datetime) -> Overview:
    since = period_start(period, now)
    return Overview(
        period=period,
        since=since,
        users=_users(session),
        plans=_plans(session, now),
        activity=[_activity(session, now, days) for days in (7, 30)],
        calls_by_task=_calls_by_task(session, since),
        money=_money(session, since),
        series=_series(session, since, monthly=period == "all"),
    )


def _users(session: Session) -> UserCounts:
    rows = session.execute(
        select(User.status, func.count()).where(User.status != "deleted").group_by(User.status)
    ).all()
    by_status = {status: int(count) for status, count in rows}
    oldest = session.scalar(select(func.min(User.waitlisted_at)).where(User.status == "waitlisted"))
    return UserCounts(
        total=sum(by_status.values()),
        by_status=by_status,
        waitlist=by_status.get("waitlisted", 0),
        oldest_wait_since=oldest,
    )


def _plans(session: Session, now: datetime) -> PlanCounts:
    month = period_start("month", now)
    cancelled = select(func.count(distinct(BillingEventRow.user_id))).where(
        BillingEventRow.type == "customer.subscription.deleted",
        BillingEventRow.outcome == "applied",
        BillingEventRow.received_at >= month,
    )
    paid_ever = exists().where(
        CreditLedgerRow.user_id == User.id, CreditLedgerRow.kind.in_(("allowance", "top_up"))
    )
    balance = func.coalesce(
        CreditBalanceRow.allowance_microusd + CreditBalanceRow.lasting_microusd, 0
    )
    active = (
        select(func.count())
        .select_from(User)
        .outerjoin(CreditBalanceRow, CreditBalanceRow.user_id == User.id)
        .where(User.status == "active", User.unmetered.is_(False))
    )
    trial = active.where(~paid_ever)
    return PlanCounts(
        subscribers=_count(session, User.subscription_status.in_(SUBSCRIBED)),
        past_due=_count(session, User.subscription_status.in_(PAST_DUE)),
        cancelled_this_month=session.scalar(cancelled) or 0,
        trial_with_credits=session.scalar(trial.where(balance > 0)) or 0,
        trial_without_credits=session.scalar(trial.where(balance <= 0)) or 0,
        zero_credits=session.scalar(active.where(balance <= 0)) or 0,
    )


def _count(session: Session, condition: ColumnElement[bool]) -> int:
    query = select(func.count()).select_from(User).where(User.status != "deleted", condition)
    return session.scalar(query) or 0


def _activity(session: Session, now: datetime, days: int) -> Activity:
    since = now - timedelta(days=days)

    def users(column: SQLColumnExpression[datetime | None]) -> int:
        query = select(func.count()).select_from(User)
        return session.scalar(query.where(User.status != "deleted", column >= since)) or 0

    games = select(func.count()).select_from(Game).where(Game.created_at >= since)
    calls = select(func.count()).select_from(LlmUsageRow).where(LlmUsageRow.created_at >= since)
    return Activity(
        days=days,
        sign_ups=users(User.created_at),
        acceptances=users(User.admitted_at),
        active_players=users(User.last_active_at),
        games_added=session.scalar(games) or 0,
        coach_calls=session.scalar(calls) or 0,
    )


def _calls_by_task(session: Session, since: datetime | None) -> dict[str, int]:
    task = func.coalesce(LlmUsageRow.task, LlmUsageRow.endpoint)
    query = select(task, func.count()).group_by(task)
    if since is not None:
        query = query.where(LlmUsageRow.created_at >= since)
    return {str(name): int(count) for name, count in session.execute(query).all()}


def _money(session: Session, since: datetime | None) -> Money:
    usage = select(
        func.coalesce(func.sum(LlmUsageRow.cost_microusd), 0),
        func.count(distinct(LlmUsageRow.user_id)),
        func.count(distinct(LlmUsageRow.game_id)),
        func.coalesce(func.sum(LlmUsageRow.input_tokens), 0),
        func.coalesce(func.sum(LlmUsageRow.cache_read_tokens), 0),
        func.coalesce(func.sum(LlmUsageRow.cache_write_tokens), 0),
    )
    if since is not None:
        usage = usage.where(LlmUsageRow.created_at >= since)
    cost, players, games, fresh, read, written = (int(v) for v in session.execute(usage).one())
    payments = sum(cents for _, cents in _payments(session, since))
    refunds = sum(cents for _, cents in _refunds(session, since))
    revenue = (payments - refunds) * MICROUSD_PER_CENT
    all_input = fresh + read + written
    return Money(
        revenue_microusd=revenue,
        refunds_microusd=refunds * MICROUSD_PER_CENT,
        api_cost_microusd=cost,
        difference_microusd=revenue - cost,
        coached_players=players,
        coached_games=games,
        cost_per_player_microusd=cost // players if players else None,
        cost_per_game_microusd=cost // games if games else None,
        credits_granted_microusd=_ledger_sum(session, since, CreditLedgerRow.kind.in_(GRANTS)),
        credits_spent_microusd=-_ledger_sum(session, since, CreditLedgerRow.kind == "usage"),
        cache_hit_rate=read / all_input if all_input else None,
    )


def _ledger_sum(session: Session, since: datetime | None, kind: ColumnElement[bool]) -> int:
    query = select(func.coalesce(func.sum(CreditLedgerRow.delta_microusd), 0)).where(kind)
    if since is not None:
        query = query.where(CreditLedgerRow.created_at >= since)
    return int(session.scalar(query) or 0)


def _payments(session: Session, since: datetime | None) -> list[tuple[datetime, int]]:
    query = select(BillingEventRow.received_at, BillingEventRow.amount_cents).where(
        BillingEventRow.type.in_(PAYMENTS),
        BillingEventRow.outcome.in_(COUNTED),
        BillingEventRow.amount_cents.is_not(None),
    )
    if since is not None:
        query = query.where(BillingEventRow.received_at >= since)
    return [(at, int(cents or 0)) for at, cents in session.execute(query).all()]


def _refunds(session: Session, since: datetime | None) -> list[tuple[datetime, int]]:
    """Money refunded, as (when, cents) increments. Each refund event carries the running total
    for its payment, so the increment is the change since that payment's previous refund (which
    may be before `since`). Refunds are rare: they're read whole and worked out here."""
    query = (
        select(
            BillingEventRow.received_at,
            BillingEventRow.amount_cents,
            func.coalesce(BillingEventRow.object_id, BillingEventRow.event_id),
        )
        .where(
            BillingEventRow.type == "charge.refunded",
            BillingEventRow.outcome.in_(COUNTED),
            BillingEventRow.amount_cents.is_not(None),
        )
        .order_by(BillingEventRow.received_at, BillingEventRow.id)
    )
    seen: dict[str, int] = defaultdict(int)
    increments: list[tuple[datetime, int]] = []
    for at, cents, payment in session.execute(query).all():
        total = -int(cents or 0)
        step = total - seen[payment]
        seen[payment] = max(seen[payment], total)
        if step > 0 and (since is None or at >= since):
            increments.append((at, step))
    return increments


def _series(session: Session, since: datetime | None, *, monthly: bool) -> list[DayMoney]:
    revenue: dict[date, int] = defaultdict(int)
    cost: dict[date, int] = defaultdict(int)
    for at, cents in _payments(session, since):
        revenue[_bucket(_as_date(at), monthly)] += cents * MICROUSD_PER_CENT
    for at, cents in _refunds(session, since):
        revenue[_bucket(_as_date(at), monthly)] -= cents * MICROUSD_PER_CENT
    day = utc_day(session, LlmUsageRow.created_at)
    query = select(day, func.coalesce(func.sum(LlmUsageRow.cost_microusd), 0)).group_by(day)
    if since is not None:
        query = query.where(LlmUsageRow.created_at >= since)
    for value, total in session.execute(query).all():
        cost[_bucket(_as_date(value), monthly)] += int(total or 0)
    days = sorted(set(revenue) | set(cost))
    return [DayMoney(day=d, revenue_microusd=revenue[d], api_cost_microusd=cost[d]) for d in days]


def utc_day(session: Session, column: SQLColumnExpression[datetime]) -> ColumnElement[object]:
    """The UTC day of a timestamp, in SQL (SQLite stores UTC text, Postgres a timestamptz)."""
    if session.get_bind().dialect.name == "postgresql":
        return func.date(func.timezone("UTC", column))
    return func.date(column)


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _bucket(day: date, monthly: bool) -> date:
    return day.replace(day=1) if monthly else day
