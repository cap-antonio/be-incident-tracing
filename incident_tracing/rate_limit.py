from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class IncidentRateLimiter:
    window_seconds: int = 300
    _last_sent_at: dict[str, float] = field(default_factory=dict)

    def should_send(self, fingerprint: str, *, now: float | None = None) -> bool:
        current_time = time.monotonic() if now is None else now
        previous_time = self._last_sent_at.get(fingerprint)
        if previous_time is not None and current_time - previous_time < self.window_seconds:
            return False

        self._last_sent_at[fingerprint] = current_time
        return True

    def release(self, fingerprint: str) -> None:
        """Release a reserved fingerprint after delivery fails."""
        self._last_sent_at.pop(fingerprint, None)
