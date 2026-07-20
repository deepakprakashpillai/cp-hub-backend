from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.shared.enums import BookingStatus


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
