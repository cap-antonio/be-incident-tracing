from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping
from html import escape
from typing import Any, Protocol

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from incident_tracing.payload import (
    build_exception_fingerprint,
    build_frontend_fingerprint,
    build_frontend_incident_payload,
    build_incident_payload,
)
from incident_tracing.rate_limit import IncidentRateLimiter

logger = logging.getLogger(__name__)


class IncidentTransport(Protocol):
    async def send_json_document(
        self,
        *,
        filename: str,
        payload: dict[str, Any],
        caption: str | None = None,
    ) -> None: ...


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
                await transport.send_json_document(
                    filename=filename,
                    payload=payload,
                    caption=_build_caption(payload),
                )
            except Exception:
                logger.exception(
                    "Incident transport failed unexpectedly",
                    extra={"request_id": request_id},
                )

        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )


def install_frontend_error_endpoint(
    app: FastAPI,
    *,
    transport: IncidentTransport,
    service_name: str,
    environment: str,
    path: str = "/incident-tracing/frontend-error",
    metadata: Mapping[str, Any] | None = None,
    shared_token: str | None = None,
    token_header_name: str = "x-incident-token",
    rate_limiter: IncidentRateLimiter | None = None,
    rate_limit_window_seconds: int = 300,
    max_payload_bytes: int = 64_000,
) -> None:
    limiter = rate_limiter or IncidentRateLimiter(window_seconds=rate_limit_window_seconds)
    router = APIRouter()

    @router.post(path, include_in_schema=False)
    async def frontend_error_endpoint(request: Request) -> JSONResponse:
        if shared_token is not None and request.headers.get(token_header_name) != shared_token:
            return JSONResponse(status_code=404, content={"detail": "Not found"})

        raw_body = await request.body()
        if len(raw_body) > max_payload_bytes:
            return JSONResponse(status_code=413, content={"detail": "Payload too large"})

        try:
            report = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JSONResponse(status_code=400, content={"detail": "Invalid JSON payload"})

        if not isinstance(report, dict):
            return JSONResponse(
                status_code=422,
                content={"detail": "Payload must be a JSON object"},
            )

        request_id = _get_request_id(request)
        payload = build_frontend_incident_payload(
            request_id=request_id,
            service_name=service_name,
            environment=environment,
            report=report,
            client_host=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            metadata=metadata,
        )

        fingerprint = build_frontend_fingerprint(report)
        if limiter.should_send(fingerprint):
            filename = f"frontend-incident-{request_id}.json"
            try:
                await transport.send_json_document(
                    filename=filename,
                    payload=payload,
                    caption=_build_frontend_caption(payload),
                )
            except Exception:
                logger.exception(
                    "Incident transport failed unexpectedly",
                    extra={"request_id": request_id},
                )

        return JSONResponse(status_code=202, content={"ok": True, "request_id": request_id})

    app.include_router(router)


def _build_frontend_caption(payload: Mapping[str, Any]) -> str:
    frontend = payload.get("frontend", {})
    message = (
        frontend.get("message", "Frontend error")
        if isinstance(frontend, Mapping)
        else "Frontend error"
    )
    url = frontend.get("url", "unknown") if isinstance(frontend, Mapping) else "unknown"
    service_name = escape(str(payload.get("service_name", "Frontend")))
    environment = escape(str(payload.get("environment", "unknown")))
    message = escape(str(message))
    url = escape(str(url))
    request_id = escape(str(payload.get("request_id", "unknown")))
    return (
        f"<b>{service_name} Incident</b>\n"
        "\n"
        f"Environment: {environment}\n"
        f"URL: {url}\n"
        f"Message: {message}\n"
        f"Request ID: {request_id}"
    )


def _build_caption(payload: Mapping[str, Any]) -> str:
    http = payload.get("http", {})
    exception = payload.get("exception", {})
    method = http.get("method", "UNKNOWN") if isinstance(http, Mapping) else "UNKNOWN"
    path = http.get("path", "unknown") if isinstance(http, Mapping) else "unknown"
    exc_type = (
        exception.get("type", "Exception")
        if isinstance(exception, Mapping)
        else "Exception"
    )
    service_name = escape(str(payload.get("service_name", "Backend")))
    environment = escape(str(payload.get("environment", "unknown")))
    method = escape(str(method))
    path = escape(str(path))
    exc_type = escape(str(exc_type))
    request_id = escape(str(payload.get("request_id", "unknown")))
    return (
        f"<b>{service_name} Incident</b>\n"
        "\n"
        f"Environment: {environment}\n"
        f"Endpoint: {method} {path}\n"
        f"Exception: {exc_type}\n"
        f"Request ID: {request_id}"
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
