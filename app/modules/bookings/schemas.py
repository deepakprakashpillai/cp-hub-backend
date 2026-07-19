from pydantic import BaseModel

from app.shared.enums import BookingStatus


class BookingCreate(BaseModel):
    student_id: str
    class_session_id: str


class BookingRead(BookingCreate):
    id: str
    status: BookingStatus
