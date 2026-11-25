"""The owner dashboard's players (SPEC_V4 §10.2): the table, searched, filtered, sorted and paged on
the server, and one player's page. Counts, money and the audit log only: never a game's moves or a
chat."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import (
    ColumnElement,
    Row,
    Select,
    SQLColumnExpression,
    and_,
    case,
    exists,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.admin.overview import PAST_DUE, SUBSCRIBED, utc_day
from app.billing.ledger import history
from app.db.models import (
    AdminActionRow,
    CreditBalanceRow,
    CreditLedgerRow,
    Game,
    LlmUsageRow,
    User,
    UserSettingsRow,
)

PAGE_SIZE = 50
RECENT = timedelta(days=30)
COST_WEEKS = 12  # the player page's cost-per-task chart
Status = Literal["waitlisted", "active", "suspended"]
Plan = Literal["subscriber", "past_due", "paid", "trial"]
Strength = Literal["standard", "deep"]
Sort = Literal[
    "name", "-name", "joined", "-joined", "last_active", "-last_active", "balance", "-balance",
    "used", "-used", "cost", "-cost", "games", "-games", "waited",
]  # fmt: skip


class UserFilters(BaseModel):
    q: str | None = None
    status: Status | None = None
    plan: Plan | None = None
    strength: Strength | None = None
    zero_credits: bool = False
    sort: Sort = "-joined"
    page: int = 1


class UserRow(BaseModel):
    id: str
    name: str
    email: str | None
    status: str
    plan: Plan
    coach_strength: Strength
    unmetered: bool
    balance_microusd: int
    used_30d_microusd: int
    cost_30d_microusd: int
    games: int
    last_active_at: datetime | None
    joined_at: datetime
    waitlisted_at: datetime | None


class UserPage(BaseModel):
    rows: list[UserRow]
    total: int
    page: int
    page_size: int


class LedgerEntry(BaseModel):
    kind: str
    credits_microusd: int
    note: str | None
    created_at: datetime
    expires_at: datetime | None


class AuditEntry(BaseModel):
    action: str
    by: str  # the owner's name, or "CLI"
    details: dict[str, Any]
    created_at: datetime


class WeekCost(BaseModel):
    week: date  # the Monday
    by_task: dict[str, int]  # microdollars


class UserDetail(BaseModel):
    row: UserRow
    allowance_microusd: int
    lasting_microusd: int
    total_cost_microusd: int
    coach_calls: int
    subscription_status: str | None
    subscription_period_end: datetime | None
    billing_customer_id: str | None
    billing_dashboard_url: str | None = None  # the customer in Stripe's dashboard
    admitted_at: datetime | None
    role: str
    cost_by_week: list[WeekCost]
    ledger: list[LedgerEntry]
    audit: list[AuditEntry]


@dataclass(frozen=True)
class _Table:
    query: Select[*tuple[Any, ...]]
    columns: dict[str, SQLColumnExpression[Any]]  # what each sort key orders by


def list_users(session: Session, filters: UserFilters, now: datetime) -> UserPage:
    table = _table(now)
    query = table.query.where(*_conditions(filters))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = max(filters.page, 1)
    ordered = query.order_by(*_order(table, filters.sort))
    rows = session.execute(ordered.limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)).all()
    return UserPage(rows=[_row(row) for row in rows], total=total, page=page, page_size=PAGE_SIZE)


def user_detail(session: Session, user_id: str, now: datetime) -> UserDetail | None:
    found = session.execute(_table(now).query.where(User.id == user_id)).first()
    user = session.get(User, user_id)
    if found is None or user is None:
        return None
    balance = session.get(CreditBalanceRow, user_id)
    cost, calls = session.execute(
        select(func.coalesce(func.sum(LlmUsageRow.cost_microusd), 0), func.count()).where(
            LlmUsageRow.user_id == user_id
        )
    ).one()
    ledger = [
        LedgerEntry(
            kind=entry.kind,
            credits_microusd=entry.delta_microusd,
            note=entry.note,
            created_at=entry.created_at,
            expires_at=entry.expires_at,
        )
        for entry in history(session, user_id, limit=100)
    ]
    return UserDetail(
        row=_row(found),
        allowance_microusd=balance.allowance_microusd if balance else 0,
        lasting_microusd=balance.lasting_microusd if balance else 0,
        total_cost_microusd=int(cost or 0),
        coach_calls=int(calls),
        subscription_status=user.subscription_status,
        subscription_period_end=user.subscription_period_end,
        billing_customer_id=user.billing_customer_id,
        admitted_at=user.admitted_at,
        role=user.role,
        cost_by_week=_cost_by_week(session, user_id, now),
        ledger=ledger,
        audit=_audit(session, user_id),
    )


def _table(now: datetime) -> _Table:
    """One row per player with the numbers the table shows and sorts by."""
    since = now - RECENT
    used_sq = (
        select(
            CreditLedgerRow.user_id.label("user_id"),
            (-func.sum(CreditLedgerRow.delta_microusd)).label("used"),
        )
        .where(CreditLedgerRow.kind == "usage", CreditLedgerRow.created_at >= since)
        .group_by(CreditLedgerRow.user_id)
        .subquery()
    )
    cost_sq = (
        select(
            LlmUsageRow.user_id.label("user_id"),
            func.sum(LlmUsageRow.cost_microusd).label("cost"),
        )
        .where(LlmUsageRow.created_at >= since)
        .group_by(LlmUsageRow.user_id)
        .subquery()
    )
    games_sq = (
        select(Game.user_id.label("user_id"), func.count().label("games"))
        .group_by(Game.user_id)
        .subquery()
    )
    used = func.coalesce(used_sq.c.used, 0)
    cost = func.coalesce(cost_sq.c.cost, 0)
    games = func.coalesce(games_sq.c.games, 0)
    query = (
        select(
            User.id,
            User.name,
            User.email,
            User.status,
            _plan().label("plan"),
            func.coalesce(UserSettingsRow.coach_strength, "standard").label("strength"),
            User.unmetered,
            _balance().label("balance"),
            used.label("used"),
            cost.label("cost"),
            games.label("games"),
            User.last_active_at,
            User.created_at,
            User.waitlisted_at,
        )
        .outerjoin(CreditBalanceRow, CreditBalanceRow.user_id == User.id)
        .outerjoin(UserSettingsRow, UserSettingsRow.user_id == User.id)
        .outerjoin(used_sq, used_sq.c.user_id == User.id)
        .outerjoin(cost_sq, cost_sq.c.user_id == User.id)
        .outerjoin(games_sq, games_sq.c.user_id == User.id)
        .where(User.status != "deleted")
    )
    columns: dict[str, SQLColumnExpression[Any]] = {
        "name": func.lower(User.name),
        "joined": User.created_at,
        "last_active": User.last_active_at,
        "balance": _balance(),
        "used": used,
        "cost": cost,
        "games": games,
    }
    return _Table(query, columns)


def _balance() -> ColumnElement[int]:
    return func.coalesce(CreditBalanceRow.allowance_microusd + CreditBalanceRow.lasting_microusd, 0)


def _plan() -> ColumnElement[str]:
    paid_ever = exists().where(
        CreditLedgerRow.user_id == User.id, CreditLedgerRow.kind.in_(("allowance", "top_up"))
    )
    return case(
        (User.subscription_status.in_(SUBSCRIBED), "subscriber"),
        (User.subscription_status.in_(PAST_DUE), "past_due"),
        (paid_ever, "paid"),
        else_="trial",
    )


def _conditions(filters: UserFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.q and filters.q.strip():
        term = f"%{_escape(filters.q.strip().lower())}%"
        conditions.append(
            or_(
                func.lower(User.name).like(term, escape="\\"),
                func.lower(func.coalesce(User.email, "")).like(term, escape="\\"),
            )
        )
    if filters.status:
        conditions.append(User.status == filters.status)
    if filters.plan:
        conditions.append(_plan() == filters.plan)
    if filters.strength == "deep":
        conditions.append(UserSettingsRow.coach_strength == "deep")
    elif filters.strength == "standard":
        conditions.append(
            or_(UserSettingsRow.coach_strength.is_(None), UserSettingsRow.coach_strength != "deep")
        )
    if filters.zero_credits:
        conditions.append(and_(_balance() <= 0, User.unmetered.is_(False)))
    return conditions


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _order(table: _Table, sort: Sort) -> list[SQLColumnExpression[Any]]:
    if sort == "waited":  # the waitlist: oldest first
        return [User.waitlisted_at.asc().nulls_last(), User.created_at.asc(), User.id]
    column = table.columns[sort.lstrip("-")]
    first = column.desc().nulls_last() if sort.startswith("-") else column.asc().nulls_last()
    return [first, User.id]


def _row(row: Row[Any]) -> UserRow:
    values = row._mapping
    return UserRow(
        id=values["id"],
        name=values["name"],
        email=values["email"],
        status=values["status"],
        plan=values["plan"],
        coach_strength="deep" if values["strength"] == "deep" else "standard",
        unmetered=bool(values["unmetered"]),
        balance_microusd=int(values["balance"]),
        used_30d_microusd=int(values["used"]),
        cost_30d_microusd=int(values["cost"]),
        games=int(values["games"]),
        last_active_at=values["last_active_at"],
        joined_at=values["created_at"],
        waitlisted_at=values["waitlisted_at"],
    )


def _cost_by_week(session: Session, user_id: str, now: datetime) -> list[WeekCost]:
    start = now - timedelta(weeks=COST_WEEKS)
    day = utc_day(session, LlmUsageRow.created_at)
    task = func.coalesce(LlmUsageRow.task, LlmUsageRow.endpoint)
    query = (
        select(day, task, func.coalesce(func.sum(LlmUsageRow.cost_microusd), 0))
        .where(LlmUsageRow.user_id == user_id, LlmUsageRow.created_at >= start)
        .group_by(day, task)
    )
    weeks: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for value, name, total in session.execute(query).all():
        when = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
        monday = when - timedelta(days=when.weekday())
        weeks[monday][str(name)] += int(total or 0)
    return [WeekCost(week=week, by_task=dict(weeks[week])) for week in sorted(weeks)]


def _audit(session: Session, user_id: str) -> list[AuditEntry]:
    rows = session.execute(
        select(AdminActionRow, User.name)
        .outerjoin(User, User.id == AdminActionRow.admin_user_id)
        .where(AdminActionRow.target_user_id == user_id)
        .order_by(AdminActionRow.created_at.desc(), AdminActionRow.id.desc())
        .limit(100)
    ).all()
    return [
        AuditEntry(
            action=row.action,
            by=admin_name or "CLI",
            details=dict(row.details or {}),
            created_at=row.created_at,
        )
        for row, admin_name in rows
    ]
