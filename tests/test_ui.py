from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.events import get_session

HEADERS = {"X-API-Key": "test-key"}


def send_event(client, payload):
    response = client.post("/api/v1/events", json=payload, headers=HEADERS)
    assert response.status_code == 201
    return response.json()


def test_empty_dashboard_and_static_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Your workspace is ready." in response.text
    assert "test-key" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert (
        "frame-ancestors 'none'" in response.headers["content-security-policy"]
    )
    for path in ("/static/app.css", "/static/app.js"):
        assert client.get(path).status_code == 200


def test_dashboard_filters_and_links(client, event_payload):
    first = send_event(client, event_payload)
    second = send_event(
        client,
        {
            **event_payload,
            "application": "other",
            "exception_type": "KeyError",
        },
    )
    response = client.patch(
        f"/api/v1/groups/{second['group_id']}",
        json={"status": "resolved"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    html = client.get("/?status=unresolved&application=demo").text
    assert f'href="/groups/{first["group_id"]}"' in html
    assert f'href="/groups/{second["group_id"]}"' not in html
    html = client.get("/?status=resolved").text
    assert f'href="/groups/{second["group_id"]}"' in html
    assert f'href="/groups/{first["group_id"]}"' not in html
    assert "No groups match" in client.get("/?application=missing").text
    assert client.get("/?status=bad").status_code == 422
    assert client.get("/?offset=-1").status_code == 422


def test_dashboard_pagination_preserves_filters(client, event_payload):
    for index in range(21):
        send_event(
            client, {**event_payload, "exception_type": f"Error{index}"}
        )
    html = client.get("/?status=unresolved&application=demo").text
    assert html.count('class="error-link"') == 20
    assert "status=unresolved&amp;application=demo&amp;offset=20" in html
    html = client.get("/?status=unresolved&application=demo&offset=20").text
    assert html.count('class="error-link"') == 1
    assert "Page 2" in html
    assert "status=unresolved&amp;application=demo&amp;offset=0" in html


def test_detail_selects_event_and_escapes_untrusted_text(
    client, event_payload
):
    payload = {
        **event_payload,
        "exception_type": "<script>alert(1)</script>",
        "application": '<img src=x onerror="alert(2)">',
        "message": "<script>alert(3)</script>",
        "traceback": (
            '  File "/app/test.py", line 1, in run\n<script>bad</script>'
        ),
    }
    first = send_event(client, payload)
    second = send_event(
        client,
        {
            **payload,
            "message": "new occurrence",
            "created_at": "2026-10-28T12:00:00Z",
        },
    )
    path = f"/groups/{first['group_id']}"
    response = client.get(path)
    assert response.status_code == 200
    assert f"<code>{second['id']}</code>" in response.text
    assert "&lt;script&gt;" in response.text
    assert "&lt;img" in response.text
    assert "<script>alert" not in response.text
    assert "<script>bad" not in response.text
    assert "<img src=x" not in response.text
    assert "test-key" not in response.text
    assert 'type="password"' in response.text
    endpoint = f'data-endpoint="/api/v1/groups/{first["group_id"]}"'
    assert endpoint in response.text
    response = client.get(path + f"?event_id={first['id']}")
    assert f"<code>{first['id']}</code>" in response.text
    assert "&lt;script&gt;alert(3)&lt;/script&gt;" in response.text


def test_missing_group_or_event_returns_html_404(client, event_payload):
    response = client.get(f"/groups/{uuid4()}")
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    first = send_event(client, event_payload)
    other = send_event(client, {**event_payload, "application": "other"})
    response = client.get(
        f"/groups/{first['group_id']}?event_id={other['id']}"
    )
    assert response.status_code == 404
    assert "This event is not in this group." in response.text


def test_history_pagination(client, event_payload):
    for index in range(21):
        saved = send_event(
            client,
            {
                **event_payload,
                "created_at": f"2026-10-27T12:00:{index:02d}Z",
            },
        )
    path = f"/groups/{saved['group_id']}"
    html = client.get(path).text
    assert html.count('href="?event_id=') == 20
    assert f"{path}?offset=20" in html
    html = client.get(path + "?offset=20").text
    assert html.count('href="?event_id=') == 1
    assert "Page 2" in html


def test_database_failure_has_safe_html_response(client):
    def unavailable():
        raise SQLAlchemyError("private connection details")

    client.app.dependency_overrides[get_session] = unavailable
    response = client.get("/")
    assert response.status_code == 503
    assert "Database unavailable." in response.text
    assert "private connection details" not in response.text
    assert "text/html" in response.headers["content-type"]
