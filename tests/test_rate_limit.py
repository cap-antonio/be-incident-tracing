from incident_tracing.rate_limit import IncidentRateLimiter


def test_rate_limiter_allows_first_incident_and_blocks_same_fingerprint() -> None:
    limiter = IncidentRateLimiter(window_seconds=60)

    assert limiter.should_send("ValueError:/api/items", now=100.0) is True
    assert limiter.should_send("ValueError:/api/items", now=120.0) is False


def test_rate_limiter_allows_same_fingerprint_after_window() -> None:
    limiter = IncidentRateLimiter(window_seconds=60)

    assert limiter.should_send("ValueError:/api/items", now=100.0) is True
    assert limiter.should_send("ValueError:/api/items", now=161.0) is True
