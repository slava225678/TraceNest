"""Create or adopt the existing stage 2/3 events table."""

import sqlalchemy as sa
from alembic import op

revision = "0001_events"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("events"):
        columns = {col["name"] for col in inspector.get_columns("events")}
        expected = {
            "id",
            "exception_type",
            "message",
            "traceback",
            "application",
            "created_at",
        }
        if columns != expected:
            raise RuntimeError("Existing events table is not stage 2/3")
    else:
        op.create_table(
            "events",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("exception_type", sa.String(200), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("traceback", sa.Text(), nullable=False),
            sa.Column("application", sa.String(200), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), nullable=False
            ),
        )
    indexes = {
        idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes("events")
    }
    if "ix_events_created_at_id" not in indexes:
        op.create_index(
            "ix_events_created_at_id", "events", ["created_at", "id"]
        )


def downgrade():
    raise RuntimeError("Destructive downgrade is not supported")
