import json
from datetime import datetime

import httpx
import pytest

from tracenest_sdk import TraceNestClient


@pytest.fixture
def sdk_factory(monkeypatch):
    real_client = httpx.Client
    clients = []

    def factory(handler, **kwargs):
        def make_http_client(**options):
            return real_client(
                transport=httpx.MockTransport(handler), **options
            )

        monkeypatch.setattr(httpx, "Client", make_http_client)
        sdk = TraceNestClient(
            url="http://tracenest.test/",
            api_key="test-key",
            **kwargs,
        )
        clients.append(sdk)
        return sdk

    yield factory
    for sdk in clients:
        sdk.close()


def test_sdk_sends_traceback_and_metadata(sdk_factory):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(201)

    sdk = sdk_factory(handler, application="example", timeout=1.5)
    try:
        1 / 0
    except ZeroDivisionError as exc:
        assert sdk.capture_exception(exc) is True

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "http://tracenest.test/api/v1/events"
    assert request.headers["X-API-Key"] == "test-key"
    assert request.headers["Content-Type"] == "application/json"
    assert set(request.extensions["timeout"].values()) == {1.5}
    event = json.loads(request.content)
    assert event["exception_type"] == "ZeroDivisionError"
    assert event["message"] == "division by zero"
    assert event["application"] == "example"
    assert "test_sdk_sends_traceback_and_metadata" in event["traceback"]
    assert "ZeroDivisionError: division by zero" in event["traceback"]
    timestamp = datetime.fromisoformat(event["created_at"])
    assert timestamp.utcoffset() is not None
    assert timestamp.utcoffset().total_seconds() == 0
    assert set(event) == {
        "exception_type",
        "message",
        "traceback",
        "application",
        "created_at",
    }


@pytest.mark.parametrize("status", [301, 400, 401, 413, 422, 500, 503])
def test_http_errors_and_redirects_return_false(sdk_factory, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, headers={"Location": "http://another-host.test/"}
        )

    sdk = sdk_factory(handler)
    assert sdk.capture_exception(ValueError("test")) is False
    assert sdk.last_error == f"HTTP {status}"
    assert len(requests) == 1


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_network_errors_do_not_escape_or_log_keys(
    sdk_factory, error, caplog, capsys
):
    def handler(request):
        raise error("secret test-key", request=request)

    sdk = sdk_factory(handler)
    assert sdk.capture_exception(RuntimeError("original error")) is False
    expected = "timeout" if error is httpx.ReadTimeout else "network_error"
    assert sdk.last_error == expected
    assert "test-key" not in caplog.text
    output = capsys.readouterr()
    assert "test-key" not in output.out + output.err


def test_context_manager_closes_client(sdk_factory):
    sdk = sdk_factory(lambda request: httpx.Response(201))
    with sdk:
        assert sdk.capture_exception(ValueError("test")) is True
    assert sdk._http.is_closed
    assert sdk.capture_exception(ValueError("after close")) is False


def test_broken_exception_formatter_returns_false(sdk_factory):
    class BrokenError(Exception):
        def __str__(self):
            raise RuntimeError("Cannot format this error")

    sdk = sdk_factory(lambda request: pytest.fail("Unexpected request"))
    assert sdk.capture_exception(BrokenError()) is False
    assert sdk.last_error == "capture_error"


def test_capture_clears_previous_error(sdk_factory):
    responses = iter([401, 201])
    sdk = sdk_factory(lambda request: httpx.Response(next(responses)))
    assert sdk.capture_exception(ValueError("first")) is False
    assert sdk.last_error == "HTTP 401"
    assert sdk.capture_exception(ValueError("second")) is True
    assert sdk.last_error is None


def test_invalid_exception_sets_diagnostic(sdk_factory):
    sdk = sdk_factory(lambda request: pytest.fail("Unexpected request"))
    assert sdk.capture_exception(None) is False
    assert sdk.last_error == "invalid_exception"


def test_sdk_to_api_to_postgresql(client, sdk_factory):
    def handler(request):
        return client.request(
            request.method,
            request.url.path,
            content=request.content,
            headers=request.headers,
        )

    sdk = sdk_factory(handler, application="integration")
    try:
        raise ValueError("SDK integration test")
    except ValueError as exc:
        assert sdk.capture_exception(exc) is True
    events = client.get("/api/v1/events").json()
    assert len(events) == 1
    assert events[0]["application"] == "integration"
    assert events[0]["message"] == "SDK integration test"
    event_id = events[0]["id"]
    assert client.get(f"/api/v1/events/{event_id}").json() == events[0]


def test_large_unicode_exception_fits_api_limits(client, sdk_factory):
    sizes = []

    def handler(request):
        sizes.append(len(request.content))
        return client.post(
            request.url.path,
            content=request.content,
            headers=request.headers,
        )

    sdk = sdk_factory(handler, application="unicode")
    assert sdk.capture_exception(ValueError("\U0001f680" * 60_000))
    assert sizes[0] <= 128 * 1024
    event = client.get("/api/v1/events").json()[0]
    assert len(event["message"]) == 10_000
    assert len(event["traceback"]) <= 50_000


def test_null_bytes_are_removed(client, sdk_factory):
    def handler(request):
        return client.post(
            request.url.path,
            content=request.content,
            headers=request.headers,
        )

    sdk = sdk_factory(handler)
    assert sdk.capture_exception(ValueError("a\x00b"))
    event = client.get("/api/v1/events").json()[0]
    assert event["message"] == "ab"
    assert "\x00" not in event["traceback"]


@pytest.mark.parametrize(
    "options",
    [
        {"url": "ftp://example.com"},
        {"url": "http://user:password@example.com"},
        {"api_key": ""},
        {"api_key": "key\ninvalid"},
        {"timeout": 0},
        {"timeout": float("inf")},
        {"application": " "},
        {"application": "x" * 201},
    ],
)
def test_invalid_configuration(options):
    config = {"url": "http://localhost:8000", "api_key": "test-key"}
    with pytest.raises(ValueError):
        TraceNestClient(**(config | options))
