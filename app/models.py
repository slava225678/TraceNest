from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ErrorGroup(Base):
    __tablename__ = "error_groups"
    __table_args__ = (
        CheckConstraint("occurrences > 0", name="ck_group_occurrences"),
        CheckConstraint("first_seen <= last_seen", name="ck_group_dates"),
        CheckConstraint(
            "status IN ('unresolved', 'resolved')", name="ck_group_status"
        ),
        Index("ix_groups_last_seen_id", "last_seen", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    exception_type: Mapped[str] = mapped_column(String(200))
    application: Mapped[str | None] = mapped_column(String(200))
    occurrences: Mapped[int] = mapped_column(BigInteger)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), default="unresolved")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_created_at_id", "created_at", "id"),
        Index("ix_events_group_created_id", "group_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("error_groups.id"))
    exception_type: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    traceback: Mapped[str] = mapped_column(Text)
    application: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
