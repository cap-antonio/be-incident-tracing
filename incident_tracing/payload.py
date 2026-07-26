from __future__ import annotations

import traceback
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from incident_tracing.sanitizer import sanitize


def build_incident_payload(
    *,
    request_id: str,
    service_name: str,
    environment: str,
    method: str,
    path: str,
    query: Mapping[str, Any],
    headers: Mapping[str, Any],
    body: Any,
    client_host: str | None,
    exc: BaseException,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "service_name": service_name,
        "environment": environment,
        "http": {
            "method": method,
            "path": path,
            "query": sanitize(dict(query)),
            "status_code": 500,
            "headers": sanitize(dict(headers)),
            "body": sanitize(body),
            "client_host": client_host,
        },
        "exception": {
            "type": exc.__class__.__name__,
            "message": str(exc),
            "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        },
        "metadata": sanitize(dict(metadata or {})),
    }


def build_frontend_incident_payload(
    *,
    request_id: str,
    service_name: str,
    environment: str,
    report: Mapping[str, Any],
    client_host: str | None,
    user_agent: str | None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "frontend",
        "service_name": service_name,
        "environment": environment,
        "frontend": sanitize(dict(report)),
        "client": {
            "host": client_host,
            "user_agent": user_agent,
        },
        "metadata": sanitize(dict(metadata or {})),
    }


def build_exception_fingerprint(*, method: str, path: str, exc: BaseException) -> str:
    return f"{method}:{path}:{exc.__class__.__module__}.{exc.__class__.__name__}:{str(exc)}"


def build_frontend_fingerprint(report: Mapping[str, Any]) -> str:
    message = str(report.get("message", ""))
    stack = str(report.get("stack", ""))
    url = str(report.get("url", ""))
    return f"frontend:{message}:{stack[:500]}:{url}"
