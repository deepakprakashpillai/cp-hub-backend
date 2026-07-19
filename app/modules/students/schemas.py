from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enums import StudentProgramType, StudentStatus


def normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone info")
    return value.astimezone(UTC)


class StudentCreate(BaseModel):
    user_id: UUID
    program_type: StudentProgramType
    status: StudentStatus = StudentStatus.ENROLLED
    access_starts_at: datetime | None = None
    access_ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_access_window(self) -> "StudentCreate":
        if self.access_starts_at is not None:
            self.access_starts_at = normalize_utc_datetime(self.access_starts_at)
        if self.access_ends_at is not None:
            self.access_ends_at = normalize_utc_datetime(self.access_ends_at)
        if (
            self.access_starts_at is not None
            and self.access_ends_at is not None
            and self.access_starts_at >= self.access_ends_at
        ):
            raise ValueError("access_starts_at must be before access_ends_at")
        return self


class StudentUpdate(BaseModel):
    program_type: StudentProgramType | None = None
    status: StudentStatus | None = None
    access_starts_at: datetime | None = None
    access_ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_access_datetimes(self) -> "StudentUpdate":
        if self.access_starts_at is not None:
            self.access_starts_at = normalize_utc_datetime(self.access_starts_at)
        if self.access_ends_at is not None:
            self.access_ends_at = normalize_utc_datetime(self.access_ends_at)
        if (
            self.access_starts_at is not None
            and self.access_ends_at is not None
            and self.access_starts_at >= self.access_ends_at
        ):
            raise ValueError("access_starts_at must be before access_ends_at")
        return self


class StudentRead(BaseModel):
    id: UUID
    user_id: UUID
    program_type: StudentProgramType
    status: StudentStatus
    access_starts_at: datetime | None
    access_ends_at: datetime | None
    joined_at: datetime
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
