from __future__ import annotations

import hashlib
import json
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
    status_code: int = 500,
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
            "status_code": status_code,
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
    metadata = report.get("metadata")
    metadata_mapping = metadata if isinstance(metadata, Mapping) else {}

    def context_value(*keys: str) -> Any:
        for source in (report, metadata_mapping):
            for key in keys:
                value = source.get(key)
                if value is not None:
                    return value
        return ""

    components = [
        str(report.get("message", "")),
        str(report.get("stack", ""))[:500],
        str(report.get("url", "")),
        context_value("status", "status_code", "http_status"),
        context_value("component"),
        context_value("operation"),
    ]
    serialized = json.dumps(components, ensure_ascii=False, default=str, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"frontend:{digest}"
