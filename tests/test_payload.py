from __future__ import annotations

from incident_tracing.payload import build_incident_payload
from incident_tracing.sanitizer import MASK


def test_build_incident_payload_includes_safe_error_context() -> None:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        payload = build_incident_payload(
            request_id="req-123",
            service_name="survade-backend",
            environment="production",
            method="POST",
            path="/api/items",
            query={"token": "secret", "page": "1"},
            headers={"authorization": "Bearer secret", "x-request-id": "req-123"},
            body={"password": "secret", "name": "demo"},
            client_host="127.0.0.1",
            exc=exc,
            metadata={"deployment": "blue"},
        )

    assert payload["request_id"] == "req-123"
    assert payload["service_name"] == "survade-backend"
    assert payload["environment"] == "production"
    assert payload["http"]["method"] == "POST"
    assert payload["http"]["path"] == "/api/items"
    assert payload["http"]["status_code"] == 500
    assert payload["http"]["query"]["token"] == MASK
    assert payload["http"]["headers"]["authorization"] == MASK
    assert payload["http"]["body"]["password"] == MASK
    assert payload["http"]["body"]["name"] == "demo"
    assert payload["exception"]["type"] == "ValueError"
    assert payload["exception"]["message"] == "boom"
    assert "ValueError: boom" in payload["exception"]["traceback"]
    assert payload["metadata"] == {"deployment": "blue"}
    assert payload["timestamp"].endswith("+00:00")


def test_build_incident_payload_requires_utc_iso_timestamp() -> None:
    try:
        raise RuntimeError("broken")
    except RuntimeError as exc:
        payload = build_incident_payload(
            request_id="req-123",
            service_name="svc",
            environment="test",
            method="GET",
            path="/",
            query={},
            headers={},
            body=None,
            client_host=None,
            exc=exc,
        )

    assert "T" in payload["timestamp"]
