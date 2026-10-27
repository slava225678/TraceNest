import json
import math
import traceback
from datetime import UTC, datetime
from types import TracebackType

import httpx

MAX_BODY_BYTES = 128 * 1024


class TraceNestClient:
    """Send exceptions synchronously without propagating capture failures."""

    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        application: str | None = None,
        timeout: float = 2.0,
    ) -> None:
        base_url = httpx.URL(url)
        if base_url.scheme not in {"http", "https"} or not base_url.host:
            raise ValueError("url must be an absolute HTTP or HTTPS URL")
        if base_url.userinfo or base_url.query or base_url.fragment:
            raise ValueError("url must not contain credentials or a query")
        if not api_key or any(
            ord(char) < 33 or ord(char) > 126 for char in api_key
        ):
            raise ValueError("api_key must contain printable ASCII only")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        if application is not None:
            application = application.strip()
            if not 1 <= len(application) <= 200 or "\x00" in application:
                raise ValueError("application must contain 1-200 characters")

        self._endpoint = str(base_url).rstrip("/") + "/api/v1/events"
        self._application = application
        self.last_error: str | None = None
        self._http = httpx.Client(
            headers={"X-API-Key": api_key},
            timeout=timeout,
            follow_redirects=False,
        )

    def capture_exception(self, exc: Exception) -> bool:
        """Return True for HTTP 201; return False for capture/send failures.

        No automatic retries or logging: retries could duplicate events,
        and network exception messages can include sensitive details.
        """
        self.last_error = None
        try:
            if not isinstance(exc, Exception):
                self.last_error = "invalid_exception"
                return False
            formatted = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
            payload = {
                "exception_type": type(exc).__name__.replace("\x00", "")[:200],
                "message": str(exc).replace("\x00", "")[:10_000],
                "traceback": formatted.replace("\x00", "")[-50_000:],
                "application": self._application,
                "created_at": datetime.now(UTC).isoformat(),
            }
            body = self._encode(payload)
            while len(body) > MAX_BODY_BYTES:
                # Keep the final frames and exception summary when trimming.
                trace = payload["traceback"]
                payload["traceback"] = trace[-max(1, len(trace) // 2) :]
                body = self._encode(payload)
            response = self._http.post(
                self._endpoint,
                content=body,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code != 201:
                self.last_error = f"HTTP {response.status_code}"
                return False
            return True
        except httpx.TimeoutException:
            self.last_error = "timeout"
            return False
        except httpx.RequestError:
            self.last_error = "network_error"
            return False
        except Exception:
            # Monitoring must not replace the application's original error.
            # This also handles broken __str__ methods and a closed client.
            self.last_error = "capture_error"
            return False

    @staticmethod
    def _encode(payload: dict) -> bytes:
        return json.dumps(payload, ensure_ascii=True).encode("utf-8")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TraceNestClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self.close()
