from datetime import UTC, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enums import AvailabilitySlotSource, AvailabilitySlotStatus, DayOfWeek


def normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone info")
    return value.astimezone(UTC)


class TeacherAvailabilityRuleBase(BaseModel):
    teacher_id: UUID
    day_of_week: DayOfWeek
    start_time_utc: time
    end_time_utc: time
    slot_duration_minutes: int = Field(gt=0, le=240)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_time_range(self) -> "TeacherAvailabilityRuleBase":
        if self.start_time_utc >= self.end_time_utc:
            raise ValueError("start_time_utc must be before end_time_utc")
        return self


class TeacherAvailabilityRuleCreate(TeacherAvailabilityRuleBase):
    pass


class TeacherAvailabilityRuleUpdate(BaseModel):
    day_of_week: DayOfWeek | None = None
    start_time_utc: time | None = None
    end_time_utc: time | None = None
    slot_duration_minutes: int | None = Field(default=None, gt=0, le=240)
    is_active: bool | None = None


class TeacherAvailabilityRuleRead(TeacherAvailabilityRuleBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeacherAvailabilitySlotBase(BaseModel):
    teacher_id: UUID
    rule_id: UUID | None = None
    source: AvailabilitySlotSource = AvailabilitySlotSource.MANUAL
    starts_at: datetime
    ends_at: datetime
    status: AvailabilitySlotStatus = AvailabilitySlotStatus.AVAILABLE

    @model_validator(mode="after")
    def validate_datetime_range(self) -> "TeacherAvailabilitySlotBase":
        self.starts_at = normalize_utc_datetime(self.starts_at)
        self.ends_at = normalize_utc_datetime(self.ends_at)
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class TeacherAvailabilitySlotCreate(TeacherAvailabilitySlotBase):
    pass


class TeacherAvailabilitySlotBulkCreate(BaseModel):
    slots: list[TeacherAvailabilitySlotCreate] = Field(min_length=1, max_length=100)


class TeacherAvailabilityBlockCreate(BaseModel):
    teacher_id: UUID
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_datetime_range(self) -> "TeacherAvailabilityBlockCreate":
        self.starts_at = normalize_utc_datetime(self.starts_at)
        self.ends_at = normalize_utc_datetime(self.ends_at)
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class TeacherAvailabilitySlotUpdate(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: AvailabilitySlotStatus | None = None

    @model_validator(mode="after")
    def validate_datetime_values(self) -> "TeacherAvailabilitySlotUpdate":
        if self.starts_at is not None:
            self.starts_at = normalize_utc_datetime(self.starts_at)
        if self.ends_at is not None:
            self.ends_at = normalize_utc_datetime(self.ends_at)
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.starts_at >= self.ends_at
        ):
            raise ValueError("starts_at must be before ends_at")
        return self


class TeacherAvailabilitySlotRead(TeacherAvailabilitySlotBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
