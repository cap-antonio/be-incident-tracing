from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from incident_tracing.integrations.fastapi import install_exception_handler


class MemoryTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def send_json_document(self, *, filename: str, payload: dict[str, Any]) -> None:
        self.calls.append((filename, payload))


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
        service_name="survade-backend",
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
    filename, payload = transport.calls[0]
    assert filename.endswith(".json")
    assert payload["request_id"] == response.json()["request_id"]
    assert payload["http"]["method"] == "POST"
    assert payload["http"]["path"] == "/boom"
    assert payload["http"]["body"]["password"] == "[REDACTED]"
    assert payload["http"]["query"]["token"] == "[REDACTED]"
    assert payload["exception"]["type"] == "RuntimeError"
    assert payload["metadata"] == {"region": "eu"}


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
