from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class IncidentTracingConfig:
    service_name: str
    environment: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    rate_limit_window_seconds: int = 300
    request_body_max_bytes: int = 64_000
