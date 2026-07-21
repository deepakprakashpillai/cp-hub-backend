from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enums import BookingEventType, BookingStatus


class OneOnOneBookingCreate(BaseModel):
    student_id: UUID
    teacher_availability_slot_id: UUID


class BatchBookingCreate(BaseModel):
    student_id: UUID
    class_session_id: UUID


class BookingRead(BaseModel):
    id: UUID
    student_id: UUID
    class_session_id: UUID
    status: BookingStatus
    booked_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingActionRequest(BaseModel):
    actor_user_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)


class AdminAddStudentToClass(BookingActionRequest):
    student_id: UUID


class OneOnOneBookingReschedule(BookingActionRequest):
    teacher_availability_slot_id: UUID


class BatchBookingReschedule(BookingActionRequest):
    class_session_id: UUID


class BookingAttendanceMark(BookingActionRequest):
    status: BookingStatus

    @model_validator(mode="after")
    def validate_attendance_status(self) -> "BookingAttendanceMark":
        if self.status not in (BookingStatus.ATTENDED, BookingStatus.MISSED):
            raise ValueError("attendance status must be attended or missed")
        return self


class ClassAttendanceRecord(BaseModel):
    booking_id: UUID
    status: BookingStatus
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_attendance_status(self) -> "ClassAttendanceRecord":
        if self.status not in (BookingStatus.ATTENDED, BookingStatus.MISSED):
            raise ValueError("attendance status must be attended or missed")
        return self


class ClassAttendanceMark(BaseModel):
    actor_user_id: UUID | None = None
    records: list[ClassAttendanceRecord] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_unique_bookings(self) -> "ClassAttendanceMark":
        booking_ids = [record.booking_id for record in self.records]
        if len(set(booking_ids)) != len(booking_ids):
            raise ValueError("attendance records cannot contain duplicate booking_id values")
        return self


class BookingEventRead(BaseModel):
    id: UUID
    booking_id: UUID
    event_type: BookingEventType
    actor_user_id: UUID | None
    reason: str
    event_metadata: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
