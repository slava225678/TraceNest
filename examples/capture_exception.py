import os

from tracenest_sdk import TraceNestClient


def main() -> int:
    key_from_env = "TRACENEST_API_KEY" in os.environ
    url_from_env = "TRACENEST_URL" in os.environ
    with TraceNestClient(
        url=os.getenv("TRACENEST_URL", "http://127.0.0.1:8000"),
        api_key=os.getenv("TRACENEST_API_KEY", "development-key"),
        application="sdk-demo",
    ) as client:
        try:
            1 / 0
        except ZeroDivisionError as exc:
            sent = client.capture_exception(exc)

    if sent:
        print("Exception sent. Look for application='sdk-demo' in the API.")
        return 0
    reason = getattr(client, "last_error", "sdk_update_required")
    print(f"Event was not sent. Reason: {reason}")
    print(f"API key source: {'environment' if key_from_env else 'default'}")
    print(f"API URL source: {'environment' if url_from_env else 'default'}")
    if reason == "HTTP 401":
        print("The client key does not match the running API's key.")
        print("The example does not load .env; check your shell exports.")
    elif reason == "timeout":
        print("The request timed out. Check the address and proxy settings.")
    elif reason == "network_error":
        print("Connection failed. Check the API and proxy settings.")
    elif reason == "sdk_update_required":
        print("Update this environment: python -m pip install -e ./sdk")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
