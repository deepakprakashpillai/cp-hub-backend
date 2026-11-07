from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.modules.bookings.schemas import BookingRead
from app.modules.classes.schemas import ClassSessionRead
from app.modules.read_models.schemas import (
    AdminClassBatchGroupSummary,
    AdminClassBookingCounts,
    AdminClassRead,
    AdminClassTeacherSummary,
)
from app.modules.schedules.schemas import normalize_utc_datetime
from app.shared.enums import (
    AvailabilitySlotSource,
    AvailabilitySlotStatus,
    BookingNoteVisibility,
    DayOfWeek,
)


class TeacherAvailabilityRuleSelfCreate(BaseModel):
    day_of_week: DayOfWeek
    start_time_utc: time
    end_time_utc: time
    slot_duration_minutes: int = Field(gt=0, le=240)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_time_range(self) -> "TeacherAvailabilityRuleSelfCreate":
        if self.start_time_utc >= self.end_time_utc:
            raise ValueError("start_time_utc must be before end_time_utc")
        return self


class TeacherAvailabilitySlotSelfCreate(BaseModel):
    rule_id: UUID | None = None
    source: AvailabilitySlotSource = AvailabilitySlotSource.MANUAL
    starts_at: datetime
    ends_at: datetime
    status: AvailabilitySlotStatus = AvailabilitySlotStatus.AVAILABLE

    @model_validator(mode="after")
    def validate_datetime_range(self) -> "TeacherAvailabilitySlotSelfCreate":
        self.starts_at = normalize_utc_datetime(self.starts_at)
        self.ends_at = normalize_utc_datetime(self.ends_at)
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class TeacherAvailabilitySlotSelfBulkCreate(BaseModel):
    slots: list[TeacherAvailabilitySlotSelfCreate] = Field(min_length=1, max_length=100)


class TeacherAvailabilityBlockSelfCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_datetime_range(self) -> "TeacherAvailabilityBlockSelfCreate":
        self.starts_at = normalize_utc_datetime(self.starts_at)
        self.ends_at = normalize_utc_datetime(self.ends_at)
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class StudentOneOnOneBookingCreate(BaseModel):
    teacher_availability_slot_id: UUID


class TeacherClassSessionRead(AdminClassRead):
    """Teacher projection retains admin detail but uses the portal count field name."""

    booking_status_counts: AdminClassBookingCounts


class TeacherClassScheduleUpdate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_datetime_range(self) -> "TeacherClassScheduleUpdate":
        self.starts_at = normalize_utc_datetime(self.starts_at)
        self.ends_at = normalize_utc_datetime(self.ends_at)
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class TeacherClassCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class StudentClassSessionRead(ClassSessionRead):
    teacher: AdminClassTeacherSummary | None = None
    batch_group: AdminClassBatchGroupSummary | None = None


class StudentBookingRead(BookingRead):
    class_session: StudentClassSessionRead


class StudentTeacherSlotRead(BaseModel):
    id: UUID
    teacher_id: UUID
    rule_id: UUID | None
    source: AvailabilitySlotSource
    starts_at: datetime
    ends_at: datetime
    status: AvailabilitySlotStatus
    created_at: datetime
    updated_at: datetime
    teacher: AdminClassTeacherSummary | None = None


class StudentFeedbackRead(BaseModel):
    id: UUID
    booking_id: UUID
    class_session_id: UUID
    student_id: UUID
    teacher_id: UUID
    note: str
    visibility: BookingNoteVisibility
    created_at: datetime
    updated_at: datetime
    teacher: AdminClassTeacherSummary | None = None
    class_session: StudentClassSessionRead | None = None


class StudentBatchDayOptionRead(BaseModel):
    id: UUID
    display_label: str | None
    batch_slot: str | None
    starts_at: datetime
    ends_at: datetime
    capacity: int
    booked_count: int
    teacher: AdminClassTeacherSummary | None = None


class StudentBatchDayRead(BaseModel):
    id: UUID
    batch_group_id: UUID
    schedule_date: date
    options: list[StudentBatchDayOptionRead]
    selected_class_session_id: UUID | None


class StudentBatchDaySelection(BaseModel):
    class_session_id: UUID | None
    reason: str | None = Field(default=None, max_length=1000)
