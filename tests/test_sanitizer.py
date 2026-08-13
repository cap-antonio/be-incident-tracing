from incident_tracing.sanitizer import MASK, sanitize


def test_sanitize_masks_sensitive_keys_case_insensitively() -> None:
    payload = {
        "Authorization": "Bearer secret",
        "password": "plain",
        "nested": {
            "OpenAI_API_Key": "fake-openai-key",
            "items": [{"refresh_token": "refresh"}, {"safe": "value"}],
        },
    }

    assert sanitize(payload) == {
        "Authorization": MASK,
        "password": MASK,
        "nested": {
            "OpenAI_API_Key": MASK,
            "items": [{"refresh_token": MASK}, {"safe": "value"}],
        },
    }


def test_sanitize_keeps_non_sensitive_values() -> None:
    payload = {"label": "admin user", "count": 2, "enabled": True}

    assert sanitize(payload) == payload
