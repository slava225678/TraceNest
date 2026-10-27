# TraceNest SDK

A small synchronous Python 3.12+ client for TraceNest Lite.
Install from the TraceNest repository root:

```bash
python -m pip install ./sdk
```

```python
from tracenest_sdk import TraceNestClient

with TraceNestClient(
    url="http://127.0.0.1:8000",
    api_key="development-key",
    application="my-app",
) as client:
    try:
        1 / 0
    except Exception as exc:
        delivered = client.capture_exception(exc)
```

Use the key configured on your TraceNest server. Reuse the client and close
it with a context manager or `close()` at shutdown.

`capture_exception()` returns `True` for HTTP 201, otherwise `False`.
Capture failures do not interrupt your application. `last_error` contains
a safe diagnostic such as `HTTP 401`, `timeout`, or `network_error`.
Invalid constructor configuration raises `ValueError`.

The default timeout is two seconds per HTTPX network phase. There are no
retries, queues, or background delivery. Tracebacks and messages are trimmed
to API limits; local variables and environment variables are not collected.
Exception messages and source lines can still contain sensitive information.

HTTPX honors proxy environment variables. Configure `NO_PROXY`/`no_proxy`
for loopback addresses if a proxy blocks your local server. The SDK does
not read the server's `.env` file. License: MIT (see `LICENSE`).
