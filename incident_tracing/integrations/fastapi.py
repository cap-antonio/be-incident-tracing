from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping
from typing import Any, Protocol

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from incident_tracing.payload import build_exception_fingerprint, build_incident_payload
from incident_tracing.rate_limit import IncidentRateLimiter

logger = logging.getLogger(__name__)


class IncidentTransport(Protocol):
    async def send_json_document(self, *, filename: str, payload: dict[str, Any]) -> None: ...


def install_exception_handler(
    app: FastAPI,
    *,
    transport: IncidentTransport,
    service_name: str,
    environment: str,
    metadata: Mapping[str, Any] | None = None,
    rate_limiter: IncidentRateLimiter | None = None,
    rate_limit_window_seconds: int = 300,
    request_body_max_bytes: int = 64_000,
) -> None:
    limiter = rate_limiter or IncidentRateLimiter(window_seconds=rate_limit_window_seconds)
    app.add_middleware(_BodyCaptureMiddleware)

    @app.exception_handler(Exception)
    async def incident_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.exception(
            "Unhandled exception captured by incident tracing",
            extra={"request_id": request_id},
            exc_info=exc,
        )

        body = await _read_request_body(request, max_bytes=request_body_max_bytes)
        payload = build_incident_payload(
            request_id=request_id,
            service_name=service_name,
            environment=environment,
            method=request.method,
            path=request.url.path,
            query=dict(request.query_params.multi_items()),
            headers=dict(request.headers.items()),
            body=body,
            client_host=request.client.host if request.client else None,
            exc=exc,
            metadata=metadata,
        )

        fingerprint = build_exception_fingerprint(
            method=request.method,
            path=request.url.path,
            exc=exc,
        )
        if limiter.should_send(fingerprint):
            filename = f"incident-{request_id}.json"
            try:
                await transport.send_json_document(filename=filename, payload=payload)
            except Exception:
                logger.exception(
                    "Incident transport failed unexpectedly",
                    extra={"request_id": request_id},
                )

        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )


def _get_request_id(request: Request) -> str:
    return request.headers.get("x-request-id") or str(uuid.uuid4())


async def _read_request_body(request: Request, *, max_bytes: int) -> Any:
    try:
        raw_body = request.scope.get("incident_tracing.body")
        if not isinstance(raw_body, bytes):
            raw_body = await request.body()
    except Exception:
        return None

    if not raw_body:
        return None

    truncated = len(raw_body) > max_bytes
    raw_body = raw_body[:max_bytes]

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            parsed: Any = json.loads(raw_body.decode("utf-8"))
            if truncated:
                return {"_truncated": True, "data": parsed}
            return parsed
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"_unparseable": True}

    try:
        text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        return {"_binary": True, "_truncated": truncated}

    if truncated:
        return {"_truncated": True, "text": text}
    return text


class _BodyCaptureMiddleware:
    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                await self._app(scope, receive, send)
                return
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        scope["incident_tracing.body"] = body
        replayed = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self._app(scope, replay_receive, send)
