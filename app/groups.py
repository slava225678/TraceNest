from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update

from app.events import DatabaseSession, require_api_key
from app.models import ErrorGroup, Event
from app.schemas import EventRead, GroupRead, GroupStatus, GroupUpdate

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("", response_model=list[GroupRead])
def list_groups(
    session: DatabaseSession,
    limit: Limit = 20,
    offset: Offset = 0,
    status: GroupStatus | None = None,
    application: Annotated[str | None, Query(max_length=200)] = None,
) -> list[ErrorGroup]:
    statement = select(ErrorGroup)
    if status is not None:
        statement = statement.where(ErrorGroup.status == status)
    if application is not None:
        statement = statement.where(ErrorGroup.application == application)
    statement = statement.order_by(
        ErrorGroup.last_seen.desc(), ErrorGroup.id.desc()
    )
    return list(session.scalars(statement.limit(limit).offset(offset)))


@router.get("/{group_id}", response_model=GroupRead)
def get_group(group_id: UUID, session: DatabaseSession) -> ErrorGroup:
    group = session.get(ErrorGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.get("/{group_id}/events", response_model=list[EventRead])
def list_group_events(
    group_id: UUID,
    session: DatabaseSession,
    limit: Limit = 20,
    offset: Offset = 0,
) -> list[Event]:
    get_group(group_id, session)
    statement = (
        select(Event)
        .where(Event.group_id == group_id)
        .order_by(Event.created_at.desc(), Event.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


@router.patch(
    "/{group_id}",
    response_model=GroupRead,
    dependencies=[Depends(require_api_key)],
)
def update_group(
    group_id: UUID, payload: GroupUpdate, session: DatabaseSession
) -> ErrorGroup:
    statement = (
        update(ErrorGroup)
        .where(ErrorGroup.id == group_id)
        .values(status=payload.status)
        .returning(ErrorGroup)
    )
    group = session.scalars(statement).one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    session.commit()
    session.refresh(group)
    return group
