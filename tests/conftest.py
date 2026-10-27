import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from app.main import create_app


@pytest.fixture
def isolated_engine():
    # Each test owns a random schema;
    # the application's public tables are untouched.
    url = make_url(os.environ["DATABASE_URL"])
    admin_engine = create_engine(url)
    schema = "test_" + uuid4().hex
    with admin_engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    try:
        test_url = url.update_query_dict(
            {"options": f"-csearch_path={schema}"}
        )
        engine = create_engine(test_url)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        with admin_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin_engine.dispose()


@pytest.fixture
def client(isolated_engine):
    app = create_app(
        isolated_engine.url.render_as_string(hide_password=False),
        "test-key",
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def event_payload():
    return {
        "exception_type": "ZeroDivisionError",
        "message": "division by zero",
        "traceback": (
            "Traceback (most recent call last):\n"
            "ZeroDivisionError: division by zero"
        ),
        "application": "demo",
        "created_at": "2026-10-27T15:00:00+03:00",
    }
