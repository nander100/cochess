"""Production logs (SPEC_V4 §12.3): JSON lines with the request's id, an access line per request
without the query string, nothing shaped like an email, key or token, and the request id sent back
to the browser."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.logs import JsonFormatter, redact, request_id


@pytest.mark.parametrize(
    ("text", "hidden"),
    [
        ("sent to player@example.com", "player@example.com"),
        ("key sk-ant-api03-abcDEF123", "abcDEF123"),
        ("stripe sk_live_51ABC and whsec_xyz789", "51ABC"),
        ("Authorization: Bearer eyJhbGciOi.x.y", "eyJhbGciOi"),
        ("/callback?code=4/0Ab&state=s3cret", "s3cret"),
        ("/unsubscribe?token=abc.def", "abc.def"),
    ],
)
def test_secrets_never_reach_a_log_line(text: str, hidden: str) -> None:
    assert hidden not in redact(text)


def test_a_line_is_json_with_the_request_id() -> None:
    token = request_id.set("req-12345678")
    try:
        record = logging.LogRecord(
            "app.coach", logging.WARNING, __file__, 1, "for %s", ("a@b.co",), None
        )
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id.reset(token)

    assert line["level"] == "WARNING" and line["logger"] == "app.coach"
    assert line["request_id"] == "req-12345678"
    assert line["message"] == "for [email]"
    assert line["time"].endswith("+00:00")


def test_each_request_gets_an_id_and_one_access_line_without_the_query(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.access"):
        response = client.post("/api/email/unsubscribe?token=secret.value")

    assert len(response.headers["X-Request-ID"]) >= 8
    [record] = [r for r in caplog.records if r.name == "app.access"]
    assert record.getMessage() == "POST /api/email/unsubscribe 400"
    assert "secret" not in record.getMessage()
    assert (record.method, record.status) == ("POST", 400)  # type: ignore[attr-defined]


def test_a_given_request_id_is_kept_and_a_strange_one_replaced(client: TestClient) -> None:
    kept = client.get("/api/legal/terms", headers={"X-Request-ID": "trace-abcdef12"})
    replaced = client.get("/api/legal/terms", headers={"X-Request-ID": "<script>"})

    assert kept.headers["X-Request-ID"] == "trace-abcdef12"
    assert replaced.headers["X-Request-ID"] != "<script>"


def test_healthy_health_checks_are_not_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/api/health")

    assert not [r for r in caplog.records if r.name == "app.access"]
