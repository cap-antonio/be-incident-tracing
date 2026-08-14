# be-incident-tracing

Reusable incident tracing with Telegram notifications for Python backend services.

`be-incident-tracing` captures unexpected application errors, builds sanitized JSON
incident reports, and delivers them to a Telegram chat as `.json` documents. The first
supported framework integration is FastAPI.

It can also expose a small backend endpoint for frontend applications, so browser-side
exceptions can be reported through the same incident pipeline without exposing Telegram
credentials to the client.

## Features

- FastAPI exception handler for unexpected `500` errors.
- Optional frontend error endpoint for browser or mobile clients.
- Telegram transport that sends each incident as a `.json` document.
- Safe client responses with a generated `request_id`.
- Recursive masking for common sensitive fields such as passwords, tokens, cookies,
  authorization headers, and API keys.
- In-memory debounce to avoid sending the same incident repeatedly.
- Strict Python typing.

## Requirements

- Python 3.12 or newer.
- FastAPI `0.111` or newer.
- A Telegram bot token and target chat/channel ID if you use the Telegram transport.

## Installation

From PyPI, once the package is published:

```bash
pip install be-incident-tracing
```

From a public Git repository:

```bash
pip install "be-incident-tracing @ git+https://github.com/<owner>/be-incident-tracing.git"
```

For local development:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Backend Setup With FastAPI

Create your FastAPI app as usual, then install the exception handler once during app
startup:

```python
from fastapi import FastAPI

from incident_tracing.integrations.fastapi import install_exception_handler
from incident_tracing.transports.telegram import TelegramTransport

app = FastAPI()

transport = TelegramTransport(
    bot_token=settings.TELEGRAM_BOT_TOKEN,
    chat_id=settings.TELEGRAM_ERRORS_CHAT_ID,
)

install_exception_handler(
    app,
    transport=transport,
    service_name="orders-api",
    environment=settings.APP_ENV,
    metadata={"region": "eu"},
)
```

After installation, unexpected exceptions are reported and clients receive a safe
response:

```json
{
  "detail": "Internal server error",
  "request_id": "8aa7f4e5-2d6c-47b8-a5f5-dcb44e76de85"
}
```

FastAPI `HTTPException` responses such as `400`, `401`, `403`, and `404` continue to
be handled normally by FastAPI.

## Telegram Configuration

Create a Telegram bot with BotFather, add it to the target chat or channel, and provide:

```bash
TELEGRAM_BOT_TOKEN=123456:replace-with-your-token
TELEGRAM_ERRORS_CHAT_ID=-1001234567890
```

See `.env.example` for the environment variables used in the examples.

The transport uses Telegram Bot API `sendDocument`, so incidents arrive as JSON files
instead of long chat messages. Telegram delivery failures are logged and swallowed so
they do not change your API response.

## Connecting A Frontend

Never call Telegram directly from frontend code. Frontend clients should send reports
to your backend, and the backend should forward sanitized incidents through this
package.

Install the frontend endpoint on the same FastAPI app:

```python
from incident_tracing.integrations.fastapi import install_frontend_error_endpoint
from incident_tracing.transports.telegram import TelegramTransport

transport = TelegramTransport(
    bot_token=settings.TELEGRAM_BOT_TOKEN,
    chat_id=settings.TELEGRAM_ERRORS_CHAT_ID,
)

install_frontend_error_endpoint(
    app,
    transport=transport,
    service_name="orders-web",
    environment=settings.APP_ENV,
    shared_token=settings.FRONTEND_INCIDENT_TOKEN,
)
```

By default, this registers:

```text
POST /incident-tracing/frontend-error
```

The endpoint is included in the host application's OpenAPI schema and Swagger UI by
default. Pass `include_in_schema=False` if you need to hide it.

If `shared_token` is set, clients must include:

```text
X-Incident-Token: <frontend incident token>
```

Use a token that is different from your Telegram bot token. The shared token is only a
lightweight gate for this endpoint, so keep rate limiting and payload limits enabled.

### Frontend Reporter Package

There is a companion npm package for reporting frontend errors to this endpoint:

```bash
npm install @cap-antonio/frontend-incident-reporter
```

### Browser Example

```ts
type FrontendIncident = {
  message: string;
  stack?: string;
  url: string;
  release?: string;
  metadata?: Record<string, unknown>;
};

async function reportFrontendIncident(report: FrontendIncident): Promise<void> {
  await fetch("/incident-tracing/frontend-error", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-incident-token": import.meta.env.VITE_FRONTEND_INCIDENT_TOKEN,
    },
    body: JSON.stringify(report),
  });
}

window.addEventListener("error", (event) => {
  void reportFrontendIncident({
    message: event.message,
    stack: event.error instanceof Error ? event.error.stack : undefined,
    url: window.location.href,
    release: import.meta.env.VITE_APP_RELEASE,
    metadata: { source: "window.error" },
  });
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason;
  void reportFrontendIncident({
    message: reason instanceof Error ? reason.message : String(reason),
    stack: reason instanceof Error ? reason.stack : undefined,
    url: window.location.href,
    release: import.meta.env.VITE_APP_RELEASE,
    metadata: { source: "unhandledrejection" },
  });
});
```

### Example Frontend Payload

```json
{
  "message": "Cannot read properties of undefined",
  "stack": "TypeError: Cannot read properties of undefined...",
  "url": "https://app.example.com/orders/123",
  "release": "web@1.4.2",
  "metadata": {
    "screen": "OrdersPage"
  }
}
```

Successful frontend reports return:

```json
{
  "ok": true,
  "request_id": "8aa7f4e5-2d6c-47b8-a5f5-dcb44e76de85"
}
```

## Payload Shape

Backend incident reports include:

- `request_id`
- UTC ISO timestamp
- `service_name`
- `environment`
- HTTP method, path, query, status code `500`, headers, optional request body, and
  client host
- exception type, message, and traceback
- optional metadata provided during handler installation

Frontend incident reports include:

- common incident fields
- `source: "frontend"`
- sanitized frontend report payload
- client host
- user agent
- optional backend metadata

## Data Sanitization

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

## Rate Limiting

The FastAPI integrations include simple in-memory debounce by incident fingerprint.
By default, the same backend exception or frontend report is sent at most once every
300 seconds.

```python
install_exception_handler(
    app,
    transport=transport,
    service_name="orders-api",
    environment="production",
    rate_limit_window_seconds=120,
)
```

```python
install_frontend_error_endpoint(
    app,
    transport=transport,
    service_name="orders-web",
    environment="production",
    rate_limit_window_seconds=120,
    max_payload_bytes=32_000,
)
```

The default limiter is process-local. If you run multiple workers, each worker keeps
its own debounce state.

## Development

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run checks:

```bash
ruff check .
mypy
pytest
```

Build package artifacts:

```bash
python -m build
```

## Security Notes

- Do not commit `.env` files, Telegram tokens, chat IDs from private chats, or frontend
  incident shared tokens.
- Keep the Telegram bot token only on the backend.
- Treat frontend reports as untrusted input.
- Avoid adding business secrets to `metadata`; it is sanitized, but metadata should
  still be intentionally small and operational.
