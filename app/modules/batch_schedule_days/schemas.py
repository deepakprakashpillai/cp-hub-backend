from datetime import UTC, date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.modules.bookings.schemas import BookingRead
from app.shared.enums import (
    BatchCapacityStrategy,
    BatchScheduleDayStatus,
    ClassSessionStatus,
    DayOfWeek,
)

MAX_BATCH_DAY_OPTIONS = 8
MAX_BATCH_DAY_RANGE_DAYS = 90


def normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone info")
    return value.astimezone(UTC)


class BatchScheduleDefaultOption(BaseModel):
    display_label: str = Field(min_length=1, max_length=150)
    start_time_utc: time
    duration_minutes: int = Field(gt=0, le=1440)
    teacher_id: UUID | None = None
    capacity: int | None = Field(default=None, gt=0)


class BatchScheduleDefaultsUpdate(BaseModel):
    default_option_count: int | None = Field(default=None, ge=1, le=MAX_BATCH_DAY_OPTIONS)
    default_teacher_id: UUID | None = None
    capacity_strategy: BatchCapacityStrategy | None = None
    fixed_capacity: int | None = Field(default=None, gt=0)
    option_templates: list[BatchScheduleDefaultOption] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_BATCH_DAY_OPTIONS,
    )
    model_config = ConfigDict(extra="forbid")

class BatchScheduleDefaultsRead(BaseModel):
    id: UUID
    timezone: str
    default_option_count: int
    default_teacher_id: UUID | None
    capacity_strategy: BatchCapacityStrategy
    fixed_capacity: int | None
    option_templates: list[BatchScheduleDefaultOption]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BatchDayOptionCreate(BaseModel):
    display_label: str = Field(min_length=1, max_length=150)
    starts_at: datetime
    ends_at: datetime
    teacher_id: UUID | None = None
    capacity: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_times(self) -> "BatchDayOptionCreate":
        self.starts_at = normalize_utc_datetime(self.starts_at)
        self.ends_at = normalize_utc_datetime(self.ends_at)
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class BatchDayCreate(BaseModel):
    batch_group_id: UUID
    schedule_date: date
    default_teacher_id: UUID | None = None
    actor_user_id: UUID | None = None
    options: list[BatchDayOptionCreate] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_BATCH_DAY_OPTIONS,
    )

    @model_validator(mode="after")
    def validate_option_dates_and_labels(self) -> "BatchDayCreate":
        if self.options is None:
            return self
        labels = [option.display_label.casefold() for option in self.options]
        if len(set(labels)) != len(labels):
            raise ValueError("option display labels must be unique within a batch day")
        for option in self.options:
            if option.starts_at.date() != self.schedule_date:
                raise ValueError("option starts_at must fall on schedule_date in UTC")
        return self


class BatchDayBulkOptionTemplate(BaseModel):
    display_label: str = Field(min_length=1, max_length=150)
    start_time_utc: time
    end_time_utc: time
    teacher_id: UUID | None = None
    capacity: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_times(self) -> "BatchDayBulkOptionTemplate":
        if self.start_time_utc >= self.end_time_utc:
            raise ValueError("start_time_utc must be before end_time_utc")
        return self


class BatchDayBulkCreate(BaseModel):
    batch_group_id: UUID
    starts_from: date
    starts_to: date
    weekdays: list[DayOfWeek] = Field(min_length=1, max_length=7)
    default_teacher_id: UUID | None = None
    actor_user_id: UUID | None = None
    options: list[BatchDayBulkOptionTemplate] = Field(
        min_length=1,
        max_length=MAX_BATCH_DAY_OPTIONS,
    )

    @model_validator(mode="after")
    def validate_range(self) -> "BatchDayBulkCreate":
        if self.starts_from > self.starts_to:
            raise ValueError("starts_from must be before or equal to starts_to")
        if (self.starts_to - self.starts_from).days + 1 > MAX_BATCH_DAY_RANGE_DAYS:
            raise ValueError("date range cannot exceed 90 days")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekdays cannot contain duplicates")
        labels = [option.display_label.casefold() for option in self.options]
        if len(set(labels)) != len(labels):
            raise ValueError("option display labels must be unique")
        return self


class BatchDayOptionUpdate(BaseModel):
    display_label: str | None = Field(default=None, min_length=1, max_length=150)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    teacher_id: UUID | None = None
    capacity: int | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, max_length=1000)
    actor_user_id: UUID | None = None

    @model_validator(mode="after")
    def normalize_times(self) -> "BatchDayOptionUpdate":
        if self.starts_at is not None:
            self.starts_at = normalize_utc_datetime(self.starts_at)
        if self.ends_at is not None:
            self.ends_at = normalize_utc_datetime(self.ends_at)
        return self


class BatchDayAllocationRequest(BaseModel):
    class_session_id: UUID
    actor_user_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)


class BatchDayActionRequest(BaseModel):
    actor_user_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)


class BatchDayStudentSelection(BaseModel):
    class_session_id: UUID
    reason: str | None = Field(default=None, max_length=1000)


class BatchDayTeacherSummary(BaseModel):
    id: UUID
    display_name: str
    full_name: str


class BatchDayBatchSummary(BaseModel):
    id: UUID
    name: str


class BatchDayStudentSummary(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr


class BatchDayOptionRead(BaseModel):
    id: UUID
    batch_schedule_day_id: UUID
    display_label: str
    option_order: int
    starts_at: datetime
    ends_at: datetime
    teacher_id: UUID | None
    teacher: BatchDayTeacherSummary | None
    capacity: int
    active_booking_count: int
    available_capacity: int
    status: ClassSessionStatus


class BatchScheduleDayRead(BaseModel):
    id: UUID
    batch_group_id: UUID
    batch: BatchDayBatchSummary
    schedule_date: date
    timezone: str = "UTC"
    status: BatchScheduleDayStatus
    cancelled_at: datetime | None
    cancelled_by_user_id: UUID | None
    cancel_reason: str | None
    options: list[BatchDayOptionRead]
    eligible_student_count: int
    unassigned_students: list[BatchDayStudentSummary]
    created_at: datetime
    updated_at: datetime


class BatchDayBulkCreateResult(BaseModel):
    created_count: int
    batch_days: list[BatchScheduleDayRead]


class BatchDayBulkCancelRequest(BaseModel):
    day_ids: list[UUID] = Field(min_length=1, max_length=100)
    actor_user_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_unique_days(self) -> "BatchDayBulkCancelRequest":
        if len(set(self.day_ids)) != len(self.day_ids):
            raise ValueError("day_ids cannot contain duplicates")
        return self


class BatchDayBulkCancelResult(BaseModel):
    cancelled_count: int
    already_cancelled_count: int
    batch_days: list[BatchScheduleDayRead]


class BatchDayAllocationResult(BaseModel):
    booking: BookingRead
    moved_from_booking_id: UUID | None = None


class StudentBatchScheduleDayRead(BaseModel):
    id: UUID
    batch_group_id: UUID
    batch: BatchDayBatchSummary
    schedule_date: date
    timezone: str = "UTC"
    options: list[BatchDayOptionRead]
    selected_booking_id: UUID | None
    selected_class_session_id: UUID | None
