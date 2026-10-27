from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.fingerprint_v1 import fingerprint_v1
from app.models import ErrorGroup
from app.schemas import EventCreate


def upsert_group(session: Session, payload: EventCreate) -> UUID:
    """Update the group inside the same transaction as its new event."""
    statement = insert(ErrorGroup).values(
        fingerprint=fingerprint_v1(
            payload.application,
            payload.exception_type,
            payload.traceback,
            payload.message,
        ),
        exception_type=payload.exception_type,
        application=payload.application,
        occurrences=1,
        first_seen=payload.created_at,
        last_seen=payload.created_at,
        status="unresolved",
    )
    statement = statement.on_conflict_do_update(
        index_elements=[ErrorGroup.fingerprint],
        set_={
            "occurrences": ErrorGroup.occurrences + 1,
            "first_seen": func.least(
                ErrorGroup.first_seen, statement.excluded.first_seen
            ),
            "last_seen": func.greatest(
                ErrorGroup.last_seen, statement.excluded.last_seen
            ),
            "status": "unresolved",
        },
    ).returning(ErrorGroup.id)
    return session.execute(statement).scalar_one()
