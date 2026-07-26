# be-incident-tracing

Small reusable Python package for centralized incident tracing in backend services.
When an unexpected server error happens, it builds a sanitized JSON incident report and
sends it to a Telegram chat as a `.json` document.

The first supported integration is FastAPI.

## Installation

Install directly from Git:

```text
be-incident-tracing @ git+ssh://git@github.com/cap-antonio/be-incident-tracing.git
```

Python 3.12 or newer is required.

## FastAPI usage

```python
from incident_tracing.integrations.fastapi import install_exception_handler
from incident_tracing.transports.telegram import TelegramTransport

install_exception_handler(
    app,
    transport=TelegramTransport(
        bot_token=settings.TELEGRAM_BOT_TOKEN,
        chat_id=settings.TELEGRAM_ERRORS_CHAT_ID,
    ),
    service_name="survade-backend",
    environment=settings.APP_ENV,
    metadata={"region": "eu"},
)
```

The handler is intended for unexpected `500` errors only. Regular FastAPI
`HTTPException` responses such as `400`, `401`, `403`, and `404` continue to be
handled by FastAPI as usual.

## Telegram configuration

Provide:

- `TELEGRAM_BOT_TOKEN`: token for your Telegram bot.
- `TELEGRAM_ERRORS_CHAT_ID`: target chat or channel ID.

Reports are sent with Telegram Bot API `sendDocument` as JSON files, not plain text.
Telegram delivery failures are logged and swallowed so they do not affect the API
response.

## Client response

Clients receive a safe response:

```json
{"detail": "Internal server error", "request_id": "..."}
```

Tracebacks, secrets, and internal details are not exposed to clients.

## Incident payload

The JSON report includes:

- `request_id`
- UTC ISO timestamp
- `service_name`
- `environment`
- HTTP method, path, query, status code `500`, headers, optional request body, and client host
- exception type, message, and traceback
- optional metadata passed during handler installation

Request bodies and metadata are sanitized before being sent.

## Sanitized data

Sensitive keys are masked recursively in dictionaries and lists, case-insensitively.
Examples include:

- `Authorization`
- `Cookie`
- `Set-Cookie`
- `password`
- `token`
- `secret`
- `api_key`
- `access_token`
- `refresh_token`
- `stripe_secret_key`
- `openai_api_key`

Similar key names such as `x-api-token`, `OpenAI_API_Key`, or nested token fields are
also masked.

## Rate limiting

The FastAPI integration includes a simple in-memory debounce by exception fingerprint.
By default, the same error fingerprint is sent at most once every 300 seconds.

```python
install_exception_handler(
    app,
    transport=transport,
    service_name="my-service",
    environment="production",
    rate_limit_window_seconds=120,
)
```
