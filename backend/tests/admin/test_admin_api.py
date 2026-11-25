"""The owner dashboard's API (SPEC_V4 §10, §14.3): only an owner reaches it, every action writes one
audit row, credit changes need a note and name their action, a subscription is cancelled only when
asked, and no game content is shown."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.billing.ledger import adjust_by_owner, balance
from app.db.models import AdminActionRow, CreditLedgerRow, EmailOutboxRow, Game, User
from tests import billing_fakes
from tests.admin.helpers import CREDIT, admin_app, by_name, owner_client, player, usage
from tests.analysis_flow import analyzed_game
from tests.auth_helpers import log_in
from tests.billing_fakes import FakeStripeClient

ROUTES = [
    ("GET", "/api/admin/overview"),
    ("GET", "/api/admin/users"),
    ("GET", "/api/admin/users/{id}"),
    ("POST", "/api/admin/users/accept"),
    ("POST", "/api/admin/users/{id}/accept"),
    ("POST", "/api/admin/users/{id}/suspend"),
    ("POST", "/api/admin/users/{id}/restore"),
    ("POST", "/api/admin/users/{id}/credits"),
    ("POST", "/api/admin/users/{id}/metering"),
]
BODIES = {
    "/api/admin/users/accept": {"user_ids": ["x"]},
    "/api/admin/users/{id}/suspend": {"reason": "spam"},
    "/api/admin/users/{id}/credits": {"credits": 5, "note": "hi"},
    "/api/admin/users/{id}/metering": {"unmetered": True},
}


@pytest.fixture
def app() -> FastAPI:
    return admin_app()


@pytest.fixture
def owner(app: FastAPI) -> TestClient:
    return owner_client(app)


def _owner_id(app: FastAPI) -> str:
    with app.state.session_factory() as session:
        return by_name(session, "Owner").id


def _audit(app: FastAPI, user_id: str) -> list[AdminActionRow]:
    with app.state.session_factory() as session:
        query = select(AdminActionRow).where(AdminActionRow.target_user_id == user_id)
        return list(session.scalars(query.order_by(AdminActionRow.id)))


def _user(app: FastAPI, user_id: str) -> User:
    with app.state.session_factory() as session:
        user = session.get(User, user_id)
        assert user is not None
        session.expunge(user)
        return user


def _subscriber(app: FastAPI) -> str:
    user_id = player(app, "Subscriber")
    with app.state.session_factory() as session:
        user = session.get(User, user_id)
        assert user is not None
        user.billing_customer_id, user.subscription_status = "cus_sub", "active"
        session.commit()
    return user_id


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_a_player_gets_not_found_on_every_owner_route(app: FastAPI, method: str, path: str) -> None:
    client = log_in(app, "Player")
    target = player(app, "Target", status="waitlisted")

    response = client.request(method, path.replace("{id}", target), json=BODIES.get(path))

    assert response.status_code == 404
    assert _audit(app, target) == []
    assert _user(app, target).status == "waitlisted"


def test_a_paused_owner_is_not_let_in(app: FastAPI, owner: TestClient) -> None:
    with app.state.session_factory() as session:
        by_name(session, "Owner").status = "suspended"
        session.commit()

    assert owner.get("/api/admin/overview").status_code == 404
    assert owner.get("/api/admin/users").status_code == 404


def test_the_overview_answers_for_each_period(owner: TestClient) -> None:
    for period in ("7d", "30d", "month", "all"):
        body = owner.get("/api/admin/overview", params={"period": period}).json()
        assert body["period"] == period
        assert body["users"]["total"] == 1
    assert owner.get("/api/admin/overview", params={"period": "year"}).status_code == 422


def test_the_users_table_searches_sorts_and_pages(app: FastAPI, owner: TestClient) -> None:
    player(app, "Ana Waiting", status="waitlisted", email="ana@example.com",
           waitlisted_at=datetime(2026, 11, 1, tzinfo=UTC))  # fmt: skip
    player(app, "Bo Paused", status="suspended", email="bo@example.com")
    player(app, "Cy 100%", email="cy@example.com")
    for i in range(55):
        player(app, f"Filler {i:02}")

    def names(**params: object) -> list[str]:
        body = owner.get("/api/admin/users", params=params).json()
        return [row["name"] for row in body["rows"]]

    assert names(q="ANA@EXAMPLE") == ["Ana Waiting"]
    assert names(q="100%") == ["Cy 100%"]  # % is matched literally
    assert names(q="%") == ["Cy 100%"]
    assert names(status="suspended") == ["Bo Paused"]
    assert names(status="waitlisted", sort="waited") == ["Ana Waiting"]
    first = owner.get("/api/admin/users", params={"sort": "name"}).json()
    assert (first["total"], len(first["rows"]), first["page_size"]) == (59, 50, 50)
    second = owner.get("/api/admin/users", params={"sort": "name", "page": 2}).json()
    assert len(second["rows"]) == 9
    assert {r["name"] for r in first["rows"]}.isdisjoint(r["name"] for r in second["rows"])
    assert names(sort="-name")[0] == "Owner"
    assert owner.get("/api/admin/users", params={"sort": "email"}).status_code == 422


def test_the_users_table_filters_by_plan_strength_and_zero_credits(
    app: FastAPI, owner: TestClient
) -> None:
    deep_client = log_in(app, "Deep")
    assert deep_client.patch("/api/settings", json={"coach_strength": "deep"}).status_code == 200
    for name in ("Trial", "Broke"):
        log_in(app, name, metered=True)
    with app.state.session_factory() as session:
        adjust_by_owner(
            session, by_name(session, "Trial"), 50 * CREDIT, note="t", now=datetime.now(UTC)
        )
        by_name(session, "Deep").subscription_status = "active"
        session.commit()

    def names(**params: object) -> set[str]:
        rows = owner.get("/api/admin/users", params=params).json()["rows"]
        return {row["name"] for row in rows}

    assert names(plan="subscriber") == {"Deep"}
    assert names(strength="deep") == {"Deep"}
    assert "Deep" not in names(strength="standard")
    assert names(zero_credits=True) == {"Broke"}  # unmetered players never count as out


def test_a_users_page_shows_numbers_and_never_game_content(app: FastAPI, owner: TestClient) -> None:
    client = log_in(app, "Gamer")
    game_id = analyzed_game(client, "white")
    with app.state.session_factory() as session:
        user = by_name(session, "Gamer")
        user.billing_customer_id = "cus_123"
        session.commit()
        user_id = user.id
        game = session.get(Game, game_id)
        assert game is not None
        headers = dict(game.headers)

    body = owner.get(f"/api/admin/users/{user_id}").json()

    assert body["row"]["games"] == 1
    assert body["billing_dashboard_url"] == "https://dashboard.stripe.com/customers/cus_123"
    text = str(body)
    assert game_id not in text
    assert all(str(value) not in text for value in headers.values() if len(str(value)) > 3)
    assert owner.get("/api/admin/users/nobody").status_code == 404


def test_the_stripe_link_points_at_test_mode_with_a_test_key() -> None:
    app = admin_app(stripe=billing_fakes.TEST_STRIPE)
    owner = owner_client(app)
    user_id = player(app, "Payer")
    with app.state.session_factory() as session:
        user = session.get(User, user_id)
        assert user is not None
        user.billing_customer_id = "cus_9"
        session.commit()

    body = owner.get(f"/api/admin/users/{user_id}").json()

    assert body["billing_dashboard_url"] == "https://dashboard.stripe.com/test/customers/cus_9"


def test_accepting_gives_the_trial_once_and_writes_one_audit_row(
    app: FastAPI, owner: TestClient
) -> None:
    waiting = player(app, "Waiting", status="waitlisted", email="w@example.com")

    body = owner.post(f"/api/admin/users/{waiting}/accept").json()
    again = owner.post(f"/api/admin/users/{waiting}/accept")

    assert body["row"]["status"] == "active"
    assert body["row"]["balance_microusd"] == 50 * CREDIT
    assert again.status_code == 409
    rows = _audit(app, waiting)
    assert [r.action for r in rows] == ["accept"]
    assert rows[0].admin_user_id == _owner_id(app)
    assert body["audit"][0]["by"] == "Owner"
    with app.state.session_factory() as session:
        query = select(func.count()).select_from(EmailOutboxRow)
        assert session.scalar(query.where(EmailOutboxRow.user_id == waiting)) == 1


def test_accepting_a_selection_skips_anyone_no_longer_waiting(
    app: FastAPI, owner: TestClient
) -> None:
    a = player(app, "A", status="waitlisted")
    b = player(app, "B", status="waitlisted")
    c = player(app, "C")

    body = owner.post("/api/admin/users/accept", json={"user_ids": [a, b, c, a, "gone"]}).json()

    assert body == {"accepted": 2, "skipped": ["C", "gone"]}
    assert [len(_audit(app, x)) for x in (a, b, c)] == [1, 1, 0]


def test_revoking_needs_a_reason_and_signs_the_player_out(app: FastAPI, owner: TestClient) -> None:
    client = log_in(app, "Spammer")
    with app.state.session_factory() as session:
        target = by_name(session, "Spammer").id
    url = f"/api/admin/users/{target}/suspend"

    assert owner.post(url, json={"reason": ""}).status_code == 422
    assert owner.post(url, json={"reason": "  "}).status_code == 409
    body = owner.post(url, json={"reason": "spam"}).json()

    assert body["row"]["status"] == "suspended"
    assert client.get("/api/me").status_code == 401
    (row,) = _audit(app, target)
    assert row.action == "suspend"
    assert row.details == {"reason": "spam", "told_reason": False, "cancelled_subscription": False}


def test_the_owner_cant_revoke_their_own_access(app: FastAPI, owner: TestClient) -> None:
    response = owner.post(f"/api/admin/users/{_owner_id(app)}/suspend", json={"reason": "oops"})

    assert response.status_code == 409
    assert _user(app, _owner_id(app)).status == "active"


def test_a_subscription_is_cancelled_only_when_the_owner_asks(
    app: FastAPI, owner: TestClient
) -> None:
    fake = billing_fakes.install(app, FakeStripeClient())
    fake.subscriptions.listed = [SimpleNamespace(id="sub_1", status="active")]
    target = _subscriber(app)

    owner.post(f"/api/admin/users/{target}/suspend", json={"reason": "pause only"})
    assert fake.params("subscriptions.cancel") == []

    owner.post(f"/api/admin/users/{target}/restore")
    body = owner.post(
        f"/api/admin/users/{target}/suspend",
        json={"reason": "fraud", "cancel_subscription": True},
    ).json()

    assert fake.params("subscriptions.cancel") == ["sub_1"]
    assert body["audit"][0]["details"]["cancelled_subscription"] is True
    assert [r.action for r in _audit(app, target)] == ["suspend", "restore", "suspend"]


def test_when_stripe_refuses_to_cancel_nothing_changes(app: FastAPI, owner: TestClient) -> None:
    fake = billing_fakes.install(app, FakeStripeClient())

    def refuse(params: object) -> object:
        raise RuntimeError("stripe is down")

    fake.subscriptions.list = refuse  # type: ignore[method-assign]
    target = _subscriber(app)

    response = owner.post(
        f"/api/admin/users/{target}/suspend", json={"reason": "x", "cancel_subscription": True}
    )

    assert response.status_code == 502
    assert _user(app, target).status == "active"
    assert _audit(app, target) == []


def test_cancelling_needs_payments_to_be_on(app: FastAPI, owner: TestClient) -> None:
    target = _subscriber(app)

    response = owner.post(
        f"/api/admin/users/{target}/suspend", json={"reason": "x", "cancel_subscription": True}
    )

    assert response.status_code == 503
    assert _user(app, target).status == "active"


def test_restoring_brings_a_paused_player_back(app: FastAPI, owner: TestClient) -> None:
    target = player(app, "Paused", status="suspended")

    body = owner.post(f"/api/admin/users/{target}/restore").json()

    assert body["row"]["status"] == "active"
    assert owner.post(f"/api/admin/users/{target}/restore").status_code == 409
    assert [r.action for r in _audit(app, target)] == ["restore"]


def test_credit_changes_need_a_note_and_name_their_action(app: FastAPI, owner: TestClient) -> None:
    target = player(app, "Tester")
    url = f"/api/admin/users/{target}/credits"

    assert owner.post(url, json={"credits": 5, "note": ""}).status_code == 422
    assert owner.post(url, json={"credits": 5, "note": "   "}).status_code == 409
    assert owner.post(url, json={"credits": 0, "note": "zero"}).status_code == 409
    assert owner.post(url, json={"credits": 20_000, "note": "typo"}).status_code == 409
    owner.post(url, json={"credits": 25, "note": "beta tester"})
    body = owner.post(url, json={"credits": -5, "note": "correction"}).json()

    assert body["row"]["balance_microusd"] == 20 * CREDIT
    actions = _audit(app, target)
    assert [(a.action, a.details) for a in actions] == [
        ("credits", {"credits": 25, "note": "beta tester"}),
        ("credits", {"credits": -5, "note": "correction"}),
    ]
    with app.state.session_factory() as session:
        sources = session.scalars(
            select(CreditLedgerRow.source)
            .where(CreditLedgerRow.user_id == target)
            .order_by(CreditLedgerRow.id)
        ).all()
        assert balance(session, target).total == 20 * CREDIT
    assert list(sources) == [f"admin_action:{a.id}" for a in actions]
    assert [e["kind"] for e in body["ledger"]] == ["owner_removal", "owner_grant"]


def test_metering_can_be_switched_and_is_audited(app: FastAPI, owner: TestClient) -> None:
    target = player(app, "Friend")
    url = f"/api/admin/users/{target}/metering"

    assert owner.post(url, json={"unmetered": True}).json()["row"]["unmetered"] is True
    assert owner.post(url, json={"unmetered": True}).status_code == 409
    assert owner.post(url, json={"unmetered": False}).json()["row"]["unmetered"] is False
    assert [r.details for r in _audit(app, target)] == [{"unmetered": True}, {"unmetered": False}]


def test_a_failed_action_writes_no_audit_row(app: FastAPI, owner: TestClient) -> None:
    target = player(app, "Active")

    assert owner.post(f"/api/admin/users/{target}/accept").status_code == 409
    assert owner.post(f"/api/admin/users/{target}/restore").status_code == 409
    assert _audit(app, target) == []


def test_recent_numbers_count_the_last_30_days_and_the_chart_12_weeks(
    app: FastAPI, owner: TestClient
) -> None:
    target = player(app, "Spender")
    now = datetime.now(UTC)
    with app.state.session_factory() as session:
        usage(session, target, 30_000, now - timedelta(days=2))
        usage(session, target, 40_000, now - timedelta(days=45), task="synopsis")
        usage(session, target, 99_000, now - timedelta(days=100))
        session.commit()

    body = owner.get(f"/api/admin/users/{target}").json()

    assert body["row"]["cost_30d_microusd"] == 30_000
    assert body["total_cost_microusd"] == 169_000
    assert body["coach_calls"] == 3
    weeks = body["cost_by_week"]  # the last 12 weeks, by task
    assert sum(sum(w["by_task"].values()) for w in weeks) == 70_000
    assert {task for w in weeks for task in w["by_task"]} == {"chat", "synopsis"}
