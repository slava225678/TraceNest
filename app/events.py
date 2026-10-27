import secrets
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.grouping import upsert_group
from app.models import Event
from app.schemas import EventCreate, EventRead

router = APIRouter(prefix="/api/v1/events", tags=["events"])
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    request: Request, api_key: Annotated[str | None, Security(api_key_header)]
) -> None:
    expected = request.app.state.api_key
    if api_key is None or not secrets.compare_digest(
        api_key.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=401, detail="Invalid or missing API key"
        )


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


DatabaseSession = Annotated[Session, Depends(get_session)]


@router.post(
    "",
    response_model=EventRead,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_event(payload: EventCreate, session: DatabaseSession) -> Event:
    group_id = upsert_group(session, payload)
    event = Event(group_id=group_id, **payload.model_dump())
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.get("", response_model=list[EventRead])
def list_events(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Event]:
    statement = select(Event).order_by(
        Event.created_at.desc(), Event.id.desc()
    )
    return list(session.scalars(statement.limit(limit).offset(offset)))


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: UUID, session: DatabaseSession) -> Event:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
