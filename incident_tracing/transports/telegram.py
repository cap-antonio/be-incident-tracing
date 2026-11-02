from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

ClientFactory = Callable[[httpx.Timeout], httpx.AsyncClient]


class TelegramTransportError(RuntimeError):
    """Safe public error raised when Telegram delivery fails."""


class TelegramTransport:
    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        timeout_seconds: float = 10.0,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timeout = httpx.Timeout(timeout_seconds)
        self._client_factory = client_factory or (
            lambda timeout: httpx.AsyncClient(timeout=timeout)
        )

    async def send_json_document(
        self,
        *,
        filename: str,
        payload: dict[str, Any],
        caption: str | None = None,
    ) -> None:
        document = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
        url = f"https://api.telegram.org/bot{self._bot_token}/sendDocument"
        files = {
            "document": (filename, document, "application/json"),
        }
        data = {"chat_id": self._chat_id}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"

        try:
            async with self._client_factory(self._timeout) as client:
                response = await client.post(url, data=data, files=files)
                response.raise_for_status()
        except Exception:
            raise TelegramTransportError("Telegram delivery failed") from None
