from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

MASK = "[REDACTED]"

_SENSITIVE_EXACT_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "token",
    "secret",
    "api_key",
    "access_token",
    "refresh_token",
    "stripe_secret_key",
    "openai_api_key",
}

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
)


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    compact = normalized.replace("_", "")
    compact_exact_keys = {value.replace("_", "") for value in _SENSITIVE_EXACT_KEYS}
    has_sensitive_part = any(
        part in normalized or part.replace("_", "") in compact
        for part in _SENSITIVE_KEY_PARTS
    )
    return (
        normalized in _SENSITIVE_EXACT_KEYS
        or compact in compact_exact_keys
        or has_sensitive_part
    )


def sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: MASK if is_sensitive_key(key) else sanitize(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [sanitize(item) for item in value]

    if isinstance(value, tuple):
        return tuple(sanitize(item) for item in value)

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [sanitize(item) for item in value]

    return value
