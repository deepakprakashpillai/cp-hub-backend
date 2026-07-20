from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enums import BatchSlot, ClassSessionStatus, StudentProgramType


def normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone info")
    return value.astimezone(UTC)


class BatchClassSessionCreate(BaseModel):
    teacher_id: UUID | None = None
    batch_slot: BatchSlot
    starts_at: datetime
    ends_at: datetime
    status: ClassSessionStatus = ClassSessionStatus.SCHEDULED
    capacity: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_datetime_range(self) -> "BatchClassSessionCreate":
        self.starts_at = normalize_utc_datetime(self.starts_at)
        self.ends_at = normalize_utc_datetime(self.ends_at)
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class ClassSessionRead(BaseModel):
    id: UUID
    teacher_id: UUID | None
    teacher_availability_slot_id: UUID | None
    program_type: StudentProgramType
    batch_slot: BatchSlot | None
    starts_at: datetime
    ends_at: datetime
    status: ClassSessionStatus
    capacity: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
