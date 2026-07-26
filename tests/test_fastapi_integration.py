from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from incident_tracing.integrations.fastapi import (
    install_exception_handler,
    install_frontend_error_endpoint,
)


class MemoryTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_json_document(
        self,
        *,
        filename: str,
        payload: dict[str, Any],
        caption: str | None = None,
    ) -> None:
        self.calls.append(
            {
                "filename": filename,
                "payload": payload,
                "caption": caption,
            }
        )


def test_exception_handler_returns_safe_response_for_unexpected_errors() -> None:
    app = FastAPI()
    transport = MemoryTransport()
    install_exception_handler(
        app,
        transport=transport,
        service_name="survade-backend",
        environment="test",
    )

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret traceback")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"]
    assert "secret traceback" not in response.text


def test_exception_handler_sends_json_document_payload_to_transport() -> None:
    app = FastAPI()
    transport = MemoryTransport()
    install_exception_handler(
        app,
        transport=transport,
        service_name="SURVADE BACKEND",
        environment="test",
        metadata={"region": "eu"},
    )

    @app.post("/boom")
    async def boom(payload: dict[str, Any]) -> None:
        raise RuntimeError("send me")

    response = TestClient(app, raise_server_exceptions=False).post(
        "/boom?token=secret",
        json={"password": "secret", "name": "Ada"},
        headers={"authorization": "Bearer secret"},
    )

    assert response.status_code == 500
    assert len(transport.calls) == 1
    call = transport.calls[0]
    filename = call["filename"]
    payload = call["payload"]
    assert filename.endswith(".json")
    assert payload["request_id"] == response.json()["request_id"]
    assert payload["http"]["method"] == "POST"
    assert payload["http"]["path"] == "/boom"
    assert payload["http"]["body"]["password"] == "[REDACTED]"
    assert payload["http"]["query"]["token"] == "[REDACTED]"
    assert payload["exception"]["type"] == "RuntimeError"
    assert payload["metadata"] == {"region": "eu"}
    assert call["caption"] == (
        "<b>SURVADE BACKEND Incident</b>\n"
        "\n"
        "Environment: test\n"
        "Endpoint: POST /boom\n"
        "Exception: RuntimeError\n"
        f"Request ID: {payload['request_id']}"
    )


def test_exception_handler_escapes_caption_values() -> None:
    app = FastAPI()
    transport = MemoryTransport()
    install_exception_handler(
        app,
        transport=transport,
        service_name="Service <Admin>",
        environment="prod & eu",
    )

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("send me")

    TestClient(app, raise_server_exceptions=False).get("/boom")

    assert transport.calls[0]["caption"].startswith(
        "<b>Service &lt;Admin&gt; Incident</b>\n\n"
        "Environment: prod &amp; eu\n"
    )


def test_exception_handler_does_not_override_http_exceptions() -> None:
    app = FastAPI()
    transport = MemoryTransport()
    install_exception_handler(
        app,
        transport=transport,
        service_name="survade-backend",
        environment="test",
    )

    @app.get("/missing")
    async def missing() -> None:
        raise HTTPException(status_code=404, detail="Not found")

    response = TestClient(app, raise_server_exceptions=False).get("/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}
    assert transport.calls == []


def test_frontend_error_endpoint_returns_ok_and_sends_json_document() -> None:
    app = FastAPI()
    transport = MemoryTransport()
    install_frontend_error_endpoint(
        app,
        transport=transport,
        service_name="survade-frontend",
        environment="test",
        metadata={"region": "eu"},
    )

    response = TestClient(app).post(
        "/incident-tracing/frontend-error",
        json={
            "message": "Cannot read properties of undefined",
            "stack": "TypeError: Cannot read properties of undefined",
            "url": "https://app.example.com/orders/1",
            "metadata": {"password": "secret", "screen": "OrdersPage"},
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["ok"] is True
    assert body["request_id"]
    assert len(transport.calls) == 1
    call = transport.calls[0]
    filename = call["filename"]
    payload = call["payload"]
    assert filename.endswith(".json")
    assert filename.startswith("frontend-incident-")
    assert payload["request_id"] == body["request_id"]
    assert payload["source"] == "frontend"
    assert payload["frontend"]["message"] == "Cannot read properties of undefined"
    assert payload["frontend"]["metadata"]["password"] == "[REDACTED]"
    assert payload["frontend"]["metadata"]["screen"] == "OrdersPage"
    assert payload["metadata"] == {"region": "eu"}
    assert call["caption"] == (
        "<b>survade-frontend Incident</b>\n"
        "\n"
        "Environment: test\n"
        "URL: https://app.example.com/orders/1\n"
        "Message: Cannot read properties of undefined\n"
        f"Request ID: {payload['request_id']}"
    )


def test_frontend_error_endpoint_requires_shared_token_when_configured() -> None:
    app = FastAPI()
    transport = MemoryTransport()
    install_frontend_error_endpoint(
        app,
        transport=transport,
        service_name="survade-frontend",
        environment="test",
        shared_token="expected-token",
    )

    missing_token_response = TestClient(app).post(
        "/incident-tracing/frontend-error",
        json={"message": "boom"},
    )
    valid_token_response = TestClient(app).post(
        "/incident-tracing/frontend-error",
        json={"message": "boom"},
        headers={"x-incident-token": "expected-token"},
    )

    assert missing_token_response.status_code == 404
    assert valid_token_response.status_code == 202
    assert len(transport.calls) == 1


def test_frontend_error_endpoint_rate_limits_same_error() -> None:
    app = FastAPI()
    transport = MemoryTransport()
    install_frontend_error_endpoint(
        app,
        transport=transport,
        service_name="survade-frontend",
        environment="test",
    )
    client = TestClient(app)

    for _ in range(2):
        response = client.post(
            "/incident-tracing/frontend-error",
            json={"message": "same boom", "stack": "same stack", "url": "/same"},
        )
        assert response.status_code == 202

    assert len(transport.calls) == 1


def test_frontend_error_endpoint_rejects_too_large_payload() -> None:
    app = FastAPI()
    transport = MemoryTransport()
    install_frontend_error_endpoint(
        app,
        transport=transport,
        service_name="survade-frontend",
        environment="test",
        max_payload_bytes=20,
    )

    response = TestClient(app).post(
        "/incident-tracing/frontend-error",
        json={"message": "x" * 100},
    )

    assert response.status_code == 413
    assert transport.calls == []
