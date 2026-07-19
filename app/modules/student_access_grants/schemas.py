from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enums import StudentAccessGrantType


def normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone info")
    return value.astimezone(UTC)


class StudentAccessGrantCreate(BaseModel):
    student_id: UUID
    package_id: UUID | None = None
    grant_type: StudentAccessGrantType
    duration_days: int | None = Field(default=None, gt=0)
    access_starts_at: datetime | None = None
    extend_current_access: bool = True
    created_by_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_access_starts_at(self) -> "StudentAccessGrantCreate":
        if self.access_starts_at is not None:
            self.access_starts_at = normalize_utc_datetime(self.access_starts_at)
        return self


class StudentAccessGrantRead(BaseModel):
    id: UUID
    student_id: UUID
    package_id: UUID | None
    grant_type: StudentAccessGrantType
    duration_days: int
    access_starts_at: datetime
    access_ends_at: datetime
    created_by_user_id: UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
