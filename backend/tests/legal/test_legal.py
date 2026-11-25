"""Terms and privacy (SPEC_V4 §11): the pages are public and versioned, the profile says whether the
current terms were accepted, accepting records the version once, and a new version asks again."""

import io
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.cli import main
from app.config import LegalSettings, Settings
from app.db.models import EmailOutboxRow, TermsAcceptance, User
from app.main import create_app
from tests.auth_helpers import BASE_URL, log_in
from tests.coach_fakes import FakeCoachClient
from tests.databases import fresh_database_url, is_postgres


def _app(version: str = "2026-12-test", url: str | None = None) -> FastAPI:
    settings = Settings(
        _env_file=None,
        database_url=url or fresh_database_url(),
        legal=LegalSettings(terms_version=version),
    )
    return create_app(settings, FakeCoachClient())


@pytest.mark.parametrize("kind", ["terms", "privacy"])
def test_the_pages_are_public_and_carry_the_version(kind: str) -> None:
    response = TestClient(_app(), base_url=BASE_URL).get(f"/api/legal/{kind}")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "2026-12-test"
    assert body["markdown"].startswith("# ")


def test_an_unknown_page_is_not_found() -> None:
    assert TestClient(_app(), base_url=BASE_URL).get("/api/legal/cookies").status_code == 404


def test_the_privacy_policy_says_what_the_spec_requires() -> None:
    text = TestClient(_app(), base_url=BASE_URL).get("/api/legal/privacy").json()["markdown"]

    for needed in ("Anthropic", "Chess.com", "Lichess", "Stripe", "Google", "cookie", "13"):
        assert needed in text, needed
    assert "export" in text.lower() and "delete" in text.lower()


def test_accepting_the_current_terms_is_recorded_once() -> None:
    app = _app()
    client = log_in(app, "Reader")
    assert client.get("/api/me").json()["terms_accepted"] is False
    assert client.get("/api/me").json()["terms_version"] == "2026-12-test"

    assert client.post("/api/me/terms", json={"version": "2026-12-test"}).status_code == 204
    assert client.post("/api/me/terms", json={"version": "2026-12-test"}).status_code == 204

    assert client.get("/api/me").json()["terms_accepted"] is True
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TermsAcceptance)) == 1


def test_accepting_an_old_version_is_refused() -> None:
    client = log_in(_app(), "Reader")

    response = client.post("/api/me/terms", json={"version": "2026-11-draft"})

    assert response.status_code == 409
    assert client.get("/api/me").json()["terms_accepted"] is False


def test_a_new_version_asks_again() -> None:
    app = _app("v1")
    client = log_in(app, "Reader")
    client.post("/api/me/terms", json={"version": "v1"})
    assert client.get("/api/me").json()["terms_accepted"] is True

    app.state.settings.legal.terms_version = "v2"  # as a restart with a new LEGAL__TERMS_VERSION

    assert client.get("/api/me").json()["terms_accepted"] is False
    assert client.post("/api/me/terms", json={"version": "v1"}).status_code == 409


def test_a_waitlisted_account_can_accept_too() -> None:
    app = _app()
    client = log_in(app, "Waiting")
    with app.state.session_factory() as session:
        user = session.scalars(select(User).where(User.name == "Waiting")).one()
        user.status = "waitlisted"
        session.commit()

    assert client.post("/api/me/terms", json={"version": "2026-12-test"}).status_code == 204


def test_notify_terms_emails_everyone_who_hasnt_accepted_once(tmp_path: Path) -> None:
    url = fresh_database_url() if is_postgres() else f"sqlite:///{tmp_path / 'cli.db'}"
    app = _app("v2", url)
    accepted = log_in(app, "Accepted")
    log_in(app, "Pending")
    log_in(app, "No email")
    accepted.post("/api/me/terms", json={"version": "v2"})
    with app.state.session_factory() as session:
        for name in ("Accepted", "Pending"):
            user = session.scalars(select(User).where(User.name == name)).one()
            user.email = f"{name.lower()}@example.com"
        session.commit()
    settings = Settings(_env_file=None, database_url=url, legal=LegalSettings(terms_version="v2"))

    outputs = []
    for _ in range(2):
        out = io.StringIO()
        assert main(["notify-terms"], settings, out) == 0
        outputs.append(out.getvalue())

    with app.state.session_factory() as session:
        rows = session.scalars(select(EmailOutboxRow).where(EmailOutboxRow.kind == "terms_updated"))
        keys = [row.dedupe_key for row in rows]
    assert len(keys) == 1 and keys[0].startswith("terms_updated:v2:")
    assert "Queued 1" in outputs[0] and "Queued 0" in outputs[1]
