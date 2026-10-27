import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.events import get_session
from app.middleware import MAX_BODY_BYTES, BodySizeLimitMiddleware
from app.models import Event

HEADERS = {"X-API-Key": "test-key"}


def test_event_round_trip_and_persistence(client, event_payload):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}
    response = client.post(
        "/api/v1/events", json=event_payload, headers=HEADERS
    )
    assert response.status_code == 201
    event = response.json()
    assert event["created_at"] == "2026-10-27T12:00:00Z"
    assert event["message"] == event_payload["message"]
    assert client.get(f"/api/v1/events/{event['id']}").json() == event
    with Session(client.app.state.engine) as session:
        saved = session.scalar(select(Event))
        assert str(saved.id) == event["id"]
        assert saved.traceback == event_payload["traceback"]


def test_order_and_pagination(client, event_payload):
    for day in (25, 27, 26):
        payload = {**event_payload, "created_at": f"2026-10-{day}T12:00:00Z"}
        response = client.post("/api/v1/events", json=payload, headers=HEADERS)
        assert response.status_code == 201
    events = client.get("/api/v1/events?limit=2").json()
    assert [event["created_at"][8:10] for event in events] == ["27", "26"]
    page = client.get("/api/v1/events?limit=1&offset=2").json()
    assert page[0]["created_at"][8:10] == "25"


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_reject_unauthorized_without_writing(client, event_payload, headers):
    assert (
        client.post(
            "/api/v1/events", json=event_payload, headers=headers
        ).status_code
        == 401
    )
    with Session(client.app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"exception_type": " "},
        {"exception_type": "x" * 201},
        {"message": "x" * 10_001},
        {"message": "invalid\x00text"},
        {"traceback": ""},
        {"traceback": "x" * 50_001},
        {"application": "x" * 201},
        {"created_at": "2026-10-27T12:00:00"},
        {"unexpected": "field"},
    ],
)
def test_reject_invalid_event(client, event_payload, changes):
    response = client.post(
        "/api/v1/events", json={**event_payload, **changes}, headers=HEADERS
    )
    assert response.status_code == 422
    assert client.get("/api/v1/events").json() == []


def test_optional_application_and_empty_exception_message(
    client, event_payload
):
    event_payload.pop("application")
    event_payload["message"] = ""
    response = client.post(
        "/api/v1/events", json=event_payload, headers=HEADERS
    )
    assert response.status_code == 201
    assert response.json()["application"] is None


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_invalid_pagination(client, query):
    assert client.get(f"/api/v1/events?{query}").status_code == 422


def test_missing_and_malformed_id(client):
    assert client.get(f"/api/v1/events/{uuid4()}").status_code == 404
    assert client.get("/api/v1/events/not-a-uuid").status_code == 422


def test_body_size_limit(client):
    response = client.post(
        "/api/v1/events", content=b"x" * (MAX_BODY_BYTES + 1), headers=HEADERS
    )
    assert response.status_code == 413


def test_chunked_body_without_content_length():
    messages = iter(
        [
            {"type": "http.request", "body": b"a" * 8, "more_body": True},
            {"type": "http.request", "body": b"b" * 8, "more_body": False},
        ]
    )
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        pytest.fail("Oversized body reached the application")

    middleware = BodySizeLimitMiddleware(downstream, max_bytes=10)
    asyncio.run(middleware({"type": "http", "headers": []}, receive, send))
    assert sent[0]["status"] == 413


def test_database_errors_do_not_expose_details(client):
    def unavailable_session():
        raise SQLAlchemyError("private database connection details")

    client.app.dependency_overrides[get_session] = unavailable_session
    response = client.get("/api/v1/events")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
