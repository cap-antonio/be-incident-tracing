from __future__ import annotations

import json
import logging

import httpx
import pytest

from incident_tracing.transports.telegram import TelegramTransport, TelegramTransportError


@pytest.mark.asyncio
async def test_telegram_transport_sends_payload_as_json_document() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = TelegramTransport(
        bot_token="bot-token",
        chat_id="chat-id",
        client_factory=lambda timeout: httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        ),
    )

    await transport.send_json_document(
        filename="incident-req-123.json",
        payload={"request_id": "req-123"},
        caption="<b>ORDERS API Incident</b>\n\nEndpoint: GET /boom",
    )

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.telegram.org/botbot-token/sendDocument"
    body = request.content
    assert b'name="chat_id"' in body
    assert b"chat-id" in body
    assert b'name="caption"' in body
    assert b"ORDERS API" in body
    assert b"Endpoint: GET /boom" in body
    assert b'name="parse_mode"' in body
    assert b"HTML" in body
    assert b'name="document"; filename="incident-req-123.json"' in body
    assert json.dumps({"request_id": "req-123"}, indent=2).encode() in body


@pytest.mark.asyncio
async def test_telegram_transport_raises_send_errors_without_logging_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"ok": False, "description": "secret-response"})

    transport = TelegramTransport(
        bot_token="secret-bot-token",
        chat_id="secret-chat-id",
        client_factory=lambda timeout: httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        ),
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(TelegramTransportError, match="Telegram delivery failed"):
            await transport.send_json_document(
                filename="incident.json",
                payload={"message": "secret-user-payload"},
            )

    assert "secret-bot-token" not in caplog.text
    assert "secret-chat-id" not in caplog.text
    assert "secret-response" not in caplog.text
    assert "secret-user-payload" not in caplog.text
