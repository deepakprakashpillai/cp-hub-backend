from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.classes.schemas import ClassSessionRead
from app.shared.enums import BatchSlot, DayOfWeek

MAX_BATCH_GENERATION_DAYS = 90
MAX_BATCH_SESSIONS_PER_DAY = 3


class BatchGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    default_capacity: int = Field(gt=0)
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=1000)


class BatchGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    default_capacity: int | None = Field(default=None, gt=0)
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class BatchGroupRead(BaseModel):
    id: UUID
    name: str
    default_capacity: int
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentBatchMembershipAssign(BaseModel):
    student_id: UUID
    assigned_by_user_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)


class StudentBatchTransfer(BaseModel):
    batch_group_id: UUID
    assigned_by_user_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)


class StudentBatchMembershipRead(BaseModel):
    id: UUID
    student_id: UUID
    batch_group_id: UUID
    is_active: bool
    assigned_by_user_id: UUID | None
    assigned_at: datetime
    ended_at: datetime | None
    end_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BatchSessionGenerationTemplate(BaseModel):
    batch_slot: BatchSlot
    start_time_utc: time
    end_time_utc: time
    teacher_id: UUID | None = None
    capacity: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_time_values(self) -> "BatchSessionGenerationTemplate":
        if self.start_time_utc == self.end_time_utc:
            raise ValueError("start_time_utc and end_time_utc cannot be equal")
        return self


class BatchSessionBulkGenerate(BaseModel):
    starts_from: date
    starts_to: date
    weekdays: list[DayOfWeek] = Field(min_length=1, max_length=7)
    sessions: list[BatchSessionGenerationTemplate] = Field(
        min_length=1,
        max_length=MAX_BATCH_SESSIONS_PER_DAY,
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> "BatchSessionBulkGenerate":
        if self.starts_from > self.starts_to:
            raise ValueError("starts_from must be before or equal to starts_to")

        days_count = (self.starts_to - self.starts_from).days + 1
        if days_count > MAX_BATCH_GENERATION_DAYS:
            raise ValueError("date range cannot exceed 90 days")

        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekdays cannot contain duplicates")

        if len({session.batch_slot for session in self.sessions}) != len(self.sessions):
            raise ValueError("sessions cannot contain duplicate batch_slot values")

        return self


class BatchSessionBulkGenerateResult(BaseModel):
    created_count: int
    class_sessions: list[ClassSessionRead]
