"""Add error groups and backfill all existing events without deleting them."""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

from app.fingerprint_v1 import fingerprint_v1

revision = "0002_groups"
down_revision = "0001_events"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "error_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("exception_type", sa.String(200), nullable=False),
        sa.Column("application", sa.String(200), nullable=True),
        sa.Column("occurrences", sa.BigInteger(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.CheckConstraint("occurrences > 0", name="ck_group_occurrences"),
        sa.CheckConstraint("first_seen <= last_seen", name="ck_group_dates"),
        sa.CheckConstraint(
            "status IN ('unresolved', 'resolved')", name="ck_group_status"
        ),
    )
    op.create_index(
        "ix_groups_last_seen_id", "error_groups", ["last_seen", "id"]
    )
    op.add_column("events", sa.Column("group_id", sa.Uuid(), nullable=True))
    connection = op.get_bind()
    # Exclude legacy writers until all rows are linked and committed.
    connection.execute(sa.text("LOCK TABLE events IN ACCESS EXCLUSIVE MODE"))
    last_id = None
    while True:
        where = "" if last_id is None else "WHERE id > :last_id"
        rows = (
            connection.execute(
                sa.text(f"SELECT * FROM events {where} ORDER BY id LIMIT 500"),
                {} if last_id is None else {"last_id": last_id},
            )
            .mappings()
            .all()
        )
        if not rows:
            break
        for row in rows:
            group_id = connection.execute(
                sa.text("""
                INSERT INTO error_groups (
                    id, fingerprint, exception_type, application,
                    occurrences, first_seen, last_seen, status
                ) VALUES (
                    :id, :fingerprint, :exception_type, :application,
                    1, :created_at, :created_at, 'unresolved'
                ) ON CONFLICT (fingerprint) DO UPDATE SET
                    occurrences = error_groups.occurrences + 1,
                    first_seen = LEAST(
                        error_groups.first_seen, EXCLUDED.first_seen
                    ),
                    last_seen = GREATEST(
                        error_groups.last_seen, EXCLUDED.last_seen
                    )
                RETURNING id
            """),
                {
                    "id": uuid4(),
                    "fingerprint": fingerprint_v1(
                        row["application"],
                        row["exception_type"],
                        row["traceback"],
                        row["message"],
                    ),
                    "exception_type": row["exception_type"],
                    "application": row["application"],
                    "created_at": row["created_at"],
                },
            ).scalar_one()
            connection.execute(
                sa.text("UPDATE events SET group_id=:group_id WHERE id=:id"),
                {"group_id": group_id, "id": row["id"]},
            )
        last_id = rows[-1]["id"]
    op.alter_column("events", "group_id", nullable=False)
    op.create_foreign_key(
        "fk_events_group_id", "events", "error_groups", ["group_id"], ["id"]
    )
    op.create_index(
        "ix_events_group_created_id",
        "events",
        ["group_id", "created_at", "id"],
    )


def downgrade():
    raise RuntimeError("Destructive downgrade is not supported")
