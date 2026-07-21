from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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


class OneOnOneBookingReschedule(BookingActionRequest):
    teacher_availability_slot_id: UUID


class BatchBookingReschedule(BookingActionRequest):
    class_session_id: UUID


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
