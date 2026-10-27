from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
)

ShortText = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=200
    ),
]


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exception_type: ShortText
    message: Annotated[str, StringConstraints(strict=True, max_length=10_000)]
    traceback: Annotated[
        str, StringConstraints(strict=True, min_length=1, max_length=50_000)
    ]
    application: ShortText | None = None
    created_at: AwareDatetime

    @field_validator("exception_type", "message", "traceback", "application")
    @classmethod
    def reject_null_bytes(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("Null bytes are not allowed")
        return value

    @field_validator("created_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class EventRead(EventCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    group_id: UUID


GroupStatus = Literal["unresolved", "resolved"]


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fingerprint: str
    exception_type: str
    application: str | None
    occurrences: int
    first_seen: AwareDatetime
    last_seen: AwareDatetime
    status: GroupStatus


class GroupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GroupStatus
