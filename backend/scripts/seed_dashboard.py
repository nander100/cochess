"""Seed a scratch database with made-up players for the owner dashboard (M5 checkpoint): some on
the waitlist, some revoked, trial players, buyers and subscribers, with a year of coach calls,
credit charges and payments. No coach or Stripe calls. Run `seed_owner_games` on the same
database first for the owner's real games, then name that player with --owner.

Usage (from backend/):
    uv run python -m scripts.seed_dashboard --db /path/to/scratch.db [--players 400]
        [--owner "Owner dashboard 123456"]
"""

import argparse
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select

from app.config import Settings
from app.db.models import BillingEventRow, CreditBalanceRow, CreditLedgerRow, LlmUsageRow, User
from app.main import create_app

TASKS = ("chat", "chat", "chat", "synopsis", "moment_intro", "moment_feedback", "walkthrough")
YEAR = timedelta(days=365)
MONTH = timedelta(days=30)
CREDIT = 10_000
Rows = dict[str, list[dict[str, Any]]]


def _player(rng: random.Random, n: int, now: datetime) -> dict[str, Any]:
    joined = now - YEAR * rng.random() ** 1.5  # more recent sign-ups than old ones
    status = rng.choices(("active", "waitlisted", "suspended"), (80, 16, 4))[0]
    active = joined + (now - joined) * rng.random()
    return {
        "id": str(uuid.uuid4()), "name": f"Sample Player {n:03}",
        "name_key": f"sample player {n:03}", "email": f"sample{n:03}@example.com",
        "status": status, "role": "player",
        "unmetered": False, "created_at": joined, "updated_at": joined, "waitlisted_at": joined,
        "admitted_at": None if status == "waitlisted" else joined,
        "last_active_at": None if status == "waitlisted" else active,
        "subscription_status": None, "billing_customer_id": None, "subscription_period_end": None,
    }  # fmt: skip


def _entry(user_id: str, delta: int, kind: str, source: str, at: datetime) -> dict[str, Any]:
    bucket = "allowance" if kind in ("allowance", "expiry") else "lasting"
    return {
        "user_id": user_id, "delta_microusd": delta, "kind": kind, "source": source,
        "bucket": bucket, "created_at": at,
    }  # fmt: skip


def _event(kind: str, cents: int, at: datetime, user_id: str, object_id: str) -> dict[str, Any]:
    return {
        "provider": "stripe", "event_id": f"evt_sample_{uuid.uuid4().hex}", "type": kind,
        "user_id": user_id, "amount_cents": cents, "currency": "usd", "object_id": object_id,
        "outcome": "applied", "received_at": at,
    }  # fmt: skip


def _subscription(rng: random.Random, user: dict[str, Any], now: datetime, rows: Rows) -> list[Any]:
    """Monthly invoices from sign-up, as (when, kind, credits, source) grants."""
    user["subscription_status"] = rng.choices(("active", "past_due", "canceled"), (85, 5, 10))[0]
    user["billing_customer_id"] = f"cus_sample_{user['id'][:8]}"
    grants: list[Any] = []
    start = user["created_at"] + timedelta(days=rng.randint(0, 10))
    while start < now:
        invoice = f"in_sample_{uuid.uuid4().hex[:12]}"
        rows["events"].append(_event("invoice.paid", 1000, start, user["id"], invoice))
        grants.append((start, "allowance", 300 * CREDIT, f"stripe:{invoice}"))
        start += MONTH
    if user["subscription_status"] != "canceled":
        user["subscription_period_end"] = start
    return grants


def _year_of(rng: random.Random, user: dict[str, Any], now: datetime) -> Rows:
    """A player's trial, payments, and the coach calls their credits allowed since joining."""
    rows: Rows = {"usage": [], "ledger": [], "events": []}
    if user["status"] == "waitlisted":
        return rows
    joined: datetime = user["created_at"]
    grants: list[Any] = [(joined, "trial", 50 * CREDIT, f"trial:{user['id']}")]
    plan = rng.choices(("trial", "top_up", "monthly"), (55, 20, 25))[0]
    if plan == "monthly":
        grants += _subscription(rng, user, now, rows)
    elif plan == "top_up":
        for _ in range(rng.randint(1, 3)):
            at = joined + (now - joined) * rng.random()
            intent = f"pi_sample_{uuid.uuid4().hex[:12]}"
            rows["events"].append(_event("checkout.session.completed", 500, at, user["id"], intent))
            grants.append((at, "top_up", 150 * CREDIT, f"stripe:{intent}"))
    calls = [
        (joined + (now - joined) * rng.random(), "usage", rng.randint(1_500, 45_000), "")
        for _ in range(rng.randint(0, 260 if plan == "monthly" else 90))
    ]
    _replay(rng, user["id"], sorted(grants + calls, key=lambda item: item[0]), rows)
    return rows


def _replay(rng: random.Random, user_id: str, timeline: list[Any], rows: Rows) -> None:
    """Apply the timeline as the ledger does: a new allowance expires what's left of the last,
    calls spend the allowance first, and a call is refused once the balance is gone."""
    allowance, lasting, last_invoice = 0, 0, None
    for at, kind, amount, source in timeline:
        if kind == "usage":
            if allowance + lasting <= 0:
                continue  # refused at zero (SPEC_V4 §5.3)
            rows["usage"].append(
                {
                    "user_id": user_id, "endpoint": "chat", "task": rng.choice(TASKS),
                    "model": "claude-sonnet", "input_tokens": 3_200, "output_tokens": 420,
                    "cache_read_tokens": rng.randint(0, 6_000), "cache_write_tokens": 600,
                    "cost_microusd": amount, "created_at": at,
                }
            )  # fmt: skip
            from_allowance = min(allowance, amount)
            allowance, lasting = allowance - from_allowance, lasting - (amount - from_allowance)
            entry = _entry(user_id, -amount, "usage", f"sample:{uuid.uuid4().hex}", at)
            rows["ledger"].append({**entry, "bucket": "split" if from_allowance else "lasting"})
            continue
        if kind == "allowance":
            if last_invoice and allowance > 0:
                expiry = f"expiry:{last_invoice}"
                rows["ledger"].append(_entry(user_id, -allowance, "expiry", expiry, at))
            allowance, last_invoice = amount, source
        else:
            lasting += amount
        rows["ledger"].append(_entry(user_id, amount, kind, source, at))
    rows.setdefault("balances", []).append(
        {"user_id": user_id, "allowance_microusd": allowance, "lasting_microusd": lasting}
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--players", type=int, default=400)
    parser.add_argument("--owner", help="a player to make the owner (e.g. from seed_owner_games)")
    args = parser.parse_args()
    if args.db.resolve() == (Path.cwd() / "cochess.db").resolve():
        sys.exit("Use a scratch database, not the app's own.")

    app = create_app(Settings(database_url=f"sqlite:///{args.db}"))
    rng, now = random.Random(7), datetime.now(UTC)
    users = [_player(rng, n, now) for n in range(1, args.players + 1)]
    tables: Rows = {"usage": [], "ledger": [], "events": [], "balances": []}
    for user in users:
        for name, rows in _year_of(rng, user, now).items():
            tables[name].extend(rows)
    with app.state.session_factory() as session:
        session.execute(insert(User), users)
        for model, rows in (
            (LlmUsageRow, tables["usage"]), (CreditLedgerRow, tables["ledger"]),
            (BillingEventRow, tables["events"]),
            (CreditBalanceRow, [{**b, "updated_at": now} for b in tables["balances"]]),
        ):  # fmt: skip
            if rows:
                session.execute(insert(model), rows)
        if args.owner:
            owner = session.scalars(select(User).where(User.name == args.owner)).first()
            if owner is None:
                sys.exit(f'no player named "{args.owner}"')
            owner.role = "owner"
        session.commit()
    sys.stdout.write(
        f"Added {len(users)} sample players, {len(tables['usage'])} coach calls and "
        f"{len(tables['events'])} payments.\n"
    )


if __name__ == "__main__":
    main()
