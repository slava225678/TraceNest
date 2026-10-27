from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.fingerprint_v1 import fingerprint_v1
from app.models import ErrorGroup, Event

HEADERS = {"X-API-Key": "test-key"}


def send_event(client, payload):
    response = client.post("/api/v1/events", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()


def test_fingerprint_ignores_line_numbers_roots_and_messages():
    windows = '  File "C:\\work\\example.py", line 12, in run\n'
    linux = '  File "/app/example.py", line 99, in run\n'
    first = fingerprint_v1("demo", "ValueError", windows, "id=1")
    assert first == fingerprint_v1("demo", "ValueError", linux, "id=2")
    assert len(first) == 64
    assert first != fingerprint_v1("other", "ValueError", linux, "id=2")
    assert first != fingerprint_v1("demo", "TypeError", linux, "id=2")
    assert first != fingerprint_v1(
        "demo", "ValueError", linux.replace("run", "other"), "id=2"
    )
    assert first != fingerprint_v1(
        "demo", "ValueError", linux.replace("example.py", "other.py"), "id=2"
    )


def test_fingerprint_without_frames_uses_message():
    first = fingerprint_v1(None, "ValueError", "no frames", "one")
    assert first != fingerprint_v1(None, "ValueError", "no frames", "two")
    assert first == fingerprint_v1(None, "ValueError", "other text", "one")


def test_groups_keep_history_and_out_of_order_dates(client, event_payload):
    ids = []
    for day in (27, 25, 26):
        payload = {**event_payload, "created_at": f"2026-10-{day}T12:00:00Z"}
        saved = send_event(client, payload)
        ids.append(saved["id"])
    groups = client.get("/api/v1/groups").json()
    assert len(groups) == 1
    group = groups[0]
    assert group["occurrences"] == 3
    assert group["first_seen"] == "2026-10-25T12:00:00Z"
    assert group["last_seen"] == "2026-10-27T12:00:00Z"
    assert group["status"] == "unresolved"
    group_id = group["id"]
    assert saved["group_id"] == group_id
    assert client.get(f"/api/v1/groups/{group_id}").json() == group
    history = client.get(f"/api/v1/groups/{group_id}/events").json()
    assert {item["id"] for item in history} == set(ids)
    page = client.get(
        f"/api/v1/groups/{group_id}/events?limit=1&offset=1"
    ).json()
    assert page[0]["created_at"] == "2026-10-26T12:00:00Z"


def test_status_authentication_and_reopening(client, event_payload):
    saved = send_event(client, event_payload)
    endpoint = f"/api/v1/groups/{saved['group_id']}"
    for headers in ({}, {"X-API-Key": "wrong"}):
        response = client.patch(
            endpoint, json={"status": "resolved"}, headers=headers
        )
        assert response.status_code == 401
        assert client.get(endpoint).json()["status"] == "unresolved"
    response = client.patch(
        endpoint, json={"status": "resolved"}, headers=HEADERS
    )
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert len(client.get("/api/v1/groups?status=resolved").json()) == 1
    assert client.get("/api/v1/groups?status=unresolved").json() == []
    send_event(client, event_payload)
    group = client.get(endpoint).json()
    assert group["status"] == "unresolved"
    assert group["occurrences"] == 2


def test_application_filter_and_group_pagination(client, event_payload):
    send_event(client, event_payload)
    send_event(
        client,
        {
            **event_payload,
            "application": "other",
            "created_at": "2026-10-28T12:00:00Z",
        },
    )
    groups = client.get("/api/v1/groups?limit=1").json()
    assert groups[0]["application"] == "other"
    groups = client.get("/api/v1/groups?limit=1&offset=1").json()
    assert groups[0]["application"] == "demo"
    groups = client.get("/api/v1/groups?application=demo").json()
    assert len(groups) == 1
    assert groups[0]["occurrences"] == 1


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
        "status=invalid",
    ],
)
def test_invalid_group_query(client, query):
    assert client.get(f"/api/v1/groups?{query}").status_code == 422


def test_missing_groups_and_invalid_updates(client, event_payload):
    missing = f"/api/v1/groups/{uuid4()}"
    assert client.get(missing).status_code == 404
    assert client.get(missing + "/events").status_code == 404
    assert (
        client.patch(
            missing, json={"status": "resolved"}, headers=HEADERS
        ).status_code
        == 404
    )
    assert client.get("/api/v1/groups/not-a-uuid").status_code == 422
    saved = send_event(client, event_payload)
    endpoint = f"/api/v1/groups/{saved['group_id']}"
    for payload in ({"status": "invalid"}, {"status": "resolved", "x": 1}):
        assert (
            client.patch(endpoint, json=payload, headers=HEADERS).status_code
            == 422
        )


def test_concurrent_requests_do_not_lose_increments(client, event_payload):
    workers = 12
    barrier = Barrier(workers)

    def send(index):
        barrier.wait(timeout=15)
        payload = {
            **event_payload,
            "created_at": f"2026-10-27T12:00:{index:02d}Z",
        }
        return send_event(client, payload)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        events = list(pool.map(send, range(workers)))
    assert len({item["group_id"] for item in events}) == 1
    group = client.get("/api/v1/groups").json()[0]
    assert group["occurrences"] == workers
    assert group["first_seen"] == "2026-10-27T12:00:00Z"
    assert group["last_seen"] == "2026-10-27T12:00:11Z"
    with Session(client.app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 12
        assert (
            session.scalar(select(func.count()).select_from(ErrorGroup)) == 1
        )


@pytest.mark.parametrize("existing", [False, True])
def test_failed_event_rolls_back_group_change(client, event_payload, existing):
    if existing:
        send_event(client, event_payload)

    def violate_database_constraint(mapper, connection, target):
        target.message = None

    event.listen(Event, "before_insert", violate_database_constraint)
    try:
        response = client.post(
            "/api/v1/events", json=event_payload, headers=HEADERS
        )
        assert response.status_code == 503
    finally:
        event.remove(Event, "before_insert", violate_database_constraint)
    groups = client.get("/api/v1/groups").json()
    if existing:
        assert len(groups) == 1
        assert groups[0]["occurrences"] == 1
    else:
        assert groups == []
