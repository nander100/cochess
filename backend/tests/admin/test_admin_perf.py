"""The owner dashboard with 10,000 players and a year of usage (SPEC_V4 §10.3): the overview and the
users page each answer in under 500 ms. Rows are written in bulk straight to the database."""

import random
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import insert

from app.db.models import (
    BillingEventRow,
    CreditBalanceRow,
    CreditLedgerRow,
    Game,
    LlmUsageRow,
    User,
    UserSettingsRow,
)
from tests.admin.helpers import admin_app, owner_client

PLAYERS = 10_000
ACTIVE = 2_000  # players who used the coach during the year
CALLS_EACH = 65  # about 130,000 coach calls
GAMES_EACH = 10
TARGET_SECONDS = 0.5
TASKS = ("chat", "synopsis", "moment_intro", "moment_feedback", "explain", "walkthrough")
STATUSES = ("active",) * 8 + ("waitlisted", "suspended")
YEAR = timedelta(days=365)


def _users(rng: random.Random, now: datetime) -> list[dict[str, Any]]:
    users = []
    for n in range(PLAYERS):
        status = rng.choice(STATUSES)
        joined = now - YEAR * rng.random()
        users.append(
            {
                "id": str(uuid.uuid4()), "name": f"Player {n:05}", "name_key": f"player {n:05}",
                "email": f"player{n}@example.com", "status": status, "role": "player",
                "unmetered": False, "created_at": joined, "updated_at": joined,
                "waitlisted_at": joined if status == "waitlisted" else None,
                "admitted_at": None if status == "waitlisted" else joined,
                "last_active_at": joined + (now - joined) * rng.random(),
                "subscription_status": rng.choice((None, None, None, "active", "past_due")),
            }
        )  # fmt: skip
    return users


def _activity(
    rng: random.Random, now: datetime, user_id: str, ledger_start: int
) -> dict[str, list[dict[str, Any]]]:
    """One active player's year: games, coach calls and their charges, balance, settings."""
    rows: dict[str, list[dict[str, Any]]] = {"games": [], "usage": [], "ledger": []}
    for _ in range(GAMES_EACH):
        rows["games"].append(
            {
                "id": str(uuid.uuid4()), "user_id": user_id, "pgn": "1. e4 e5 *",
                "user_color": "white", "elo": 1400, "headers": {}, "status": "analyzed",
                "source": "single", "created_at": now - YEAR * rng.random(),
            }
        )  # fmt: skip
    for n in range(CALLS_EACH):
        at, cost = now - YEAR * rng.random(), rng.randint(2_000, 40_000)
        rows["usage"].append(
            {
                "user_id": user_id, "endpoint": "chat", "task": rng.choice(TASKS),
                "model": "claude-sonnet", "input_tokens": 3_000, "output_tokens": 400,
                "cache_read_tokens": 2_000, "cache_write_tokens": 500,
                "cost_microusd": cost, "created_at": at,
            }
        )  # fmt: skip
        rows["ledger"].append(
            {
                "user_id": user_id, "delta_microusd": -cost, "kind": "usage",
                "source": f"llm_usage:{ledger_start + n}", "bucket": "lasting", "created_at": at,
            }
        )  # fmt: skip
    rows["balances"] = [
        {"user_id": user_id, "allowance_microusd": 0,
         "lasting_microusd": rng.randint(-50_000, 3_000_000), "updated_at": now}
    ]  # fmt: skip
    rows["settings"] = [
        {"user_id": user_id, "theme": "light", "board_scheme": "blue", "piece_set": "cburnett",
         "sounds": True, "engine_panel": False, "playback_seconds": 1.5,
         "coach_strength": rng.choice(("standard", "deep"))}
    ]  # fmt: skip
    return rows


def _generate(app: FastAPI) -> None:
    rng = random.Random(4)
    now = datetime.now(UTC)
    users = _users(rng, now)
    active = [u["id"] for u in users if u["status"] == "active"][:ACTIVE]
    tables: dict[str, list[dict[str, Any]]] = {
        "games": [], "usage": [], "ledger": [], "balances": [], "settings": []
    }  # fmt: skip
    for i, user_id in enumerate(active):
        for name, rows in _activity(rng, now, user_id, i * CALLS_EACH).items():
            tables[name].extend(rows)
    events = [
        {
            "provider": "stripe", "event_id": f"evt_{n}", "type": "invoice.paid",
            "user_id": rng.choice(active), "amount_cents": 1000, "currency": "usd",
            "object_id": f"in_{n}", "outcome": "applied", "received_at": now - YEAR * rng.random(),
        }
        for n in range(4_000)
    ]  # fmt: skip
    with app.state.session_factory() as session:
        for model, rows in (
            (User, users), (Game, tables["games"]), (LlmUsageRow, tables["usage"]),
            (CreditLedgerRow, tables["ledger"]), (CreditBalanceRow, tables["balances"]),
            (UserSettingsRow, tables["settings"]), (BillingEventRow, events),
        ):  # fmt: skip
            session.execute(insert(model), rows)
        session.commit()


def _timed(client: TestClient, url: str, **params: object) -> tuple[float, dict[str, Any]]:
    client.get(url, params=params)  # warm up (first query plans, connection)
    began = time.perf_counter()
    response = client.get(url, params=params)
    elapsed = time.perf_counter() - began
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return elapsed, body


def test_the_dashboard_answers_fast_with_ten_thousand_players() -> None:
    app = admin_app()
    owner = owner_client(app)
    _generate(app)

    timings: dict[str, float] = {}
    for period in ("30d", "all"):
        elapsed, body = _timed(owner, "/api/admin/overview", period=period)
        timings[f"overview {period}"] = elapsed
        assert body["users"]["total"] == PLAYERS + 1
    for name, params in (
        ("users newest", {}),
        ("users by cost", {"sort": "-cost"}),
        ("users search", {"q": "player 04"}),
        ("users zero credits", {"zero_credits": "true", "sort": "-used"}),
        ("waitlist", {"status": "waitlisted", "sort": "waited"}),
        ("users last page", {"sort": "name", "page": 150}),
    ):
        elapsed, body = _timed(owner, "/api/admin/users", **params)
        timings[name] = elapsed
        assert body["total"] > 0
    user_id = body["rows"][0]["id"]
    timings["a user's page"], _ = _timed(owner, f"/api/admin/users/{user_id}")

    print({name: f"{s * 1000:.0f} ms" for name, s in timings.items()})  # shown with -s
    slow = {name: f"{s * 1000:.0f} ms" for name, s in timings.items() if s >= TARGET_SECONDS}
    assert not slow, f"over {TARGET_SECONDS * 1000:.0f} ms: {slow}"
