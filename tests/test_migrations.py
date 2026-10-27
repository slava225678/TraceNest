from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.migrations import upgrade_database
from app.models import Base


def create_legacy_table(engine):
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE TABLE events (
                id UUID PRIMARY KEY,
                exception_type VARCHAR(200) NOT NULL,
                message TEXT NOT NULL,
                traceback TEXT NOT NULL,
                application VARCHAR(200),
                created_at TIMESTAMPTZ NOT NULL
            )
        """)
        )


def test_fresh_schema_matches_models(isolated_engine):
    upgrade_database(isolated_engine)
    with isolated_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


@pytest.mark.parametrize("count", [3, 501])
def test_legacy_events_survive_migration_and_second_start(
    isolated_engine, count
):
    create_legacy_table(isolated_engine)
    originals = []
    with isolated_engine.begin() as connection:
        for index in range(count):
            row = {
                "id": uuid4(),
                "exception_type": "ValueError",
                "message": f"item {index}",
                "traceback": '  File "/app/demo.py", line 12, in run\n',
                "application": "legacy",
                "created_at": datetime(2026, 10, 25 + index % 3, tzinfo=UTC),
            }
            connection.execute(
                text("""
                INSERT INTO events VALUES (
                    :id, :exception_type, :message, :traceback,
                    :application, :created_at
                )
            """),
                row,
            )
            originals.append(row)
    upgrade_database(isolated_engine)
    upgrade_database(isolated_engine)
    with isolated_engine.connect() as connection:
        saved = connection.execute(text("SELECT * FROM events")).mappings()
        saved = {row["id"]: dict(row) for row in saved}
        groups = (
            connection.execute(text("SELECT * FROM error_groups"))
            .mappings()
            .all()
        )
        assert len(groups) == 1
        group = groups[0]
        assert len(saved) == count
        assert group["occurrences"] == count
        assert group["first_seen"] == originals[0]["created_at"]
        assert group["last_seen"] == originals[-1]["created_at"]
        for original in originals:
            actual = saved[original["id"]]
            assert actual.pop("group_id") == group["id"]
            assert actual == original
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0002_groups"
        )
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_failed_backfill_is_transactional(isolated_engine, monkeypatch):
    create_legacy_table(isolated_engine)
    with isolated_engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO events VALUES (
                :id, 'ValueError', 'message', 'trace', NULL, now()
            )
        """),
            {"id": uuid4()},
        )

    def fail_fingerprint(*args):
        raise RuntimeError("Simulated backfill failure")

    monkeypatch.setattr("app.fingerprint_v1.fingerprint_v1", fail_fingerprint)
    with pytest.raises(RuntimeError, match="Simulated backfill failure"):
        upgrade_database(isolated_engine)
    inspector = inspect(isolated_engine)
    assert not inspector.has_table("error_groups")
    assert not inspector.has_table("alembic_version")
    assert "group_id" not in {
        col["name"] for col in inspector.get_columns("events")
    }
    with isolated_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
