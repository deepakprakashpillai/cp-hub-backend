from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.enums import BookingNoteVisibility


class BookingNoteCreate(BaseModel):
    # The authenticated teacher is injected by the route.  The optional field keeps
    # the schema backward-compatible for internal/admin callers.
    teacher_id: UUID | None = None
    note: str = Field(min_length=1, max_length=2000)
    visibility: BookingNoteVisibility = BookingNoteVisibility.ADMIN_ONLY

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("note cannot be blank")
        return value


class BookingNoteUpdate(BaseModel):
    note: str | None = Field(default=None, min_length=1, max_length=2000)
    visibility: BookingNoteVisibility | None = None

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("note cannot be blank")
        return value


class BookingNoteRead(BaseModel):
    id: UUID
    booking_id: UUID
    class_session_id: UUID
    student_id: UUID
    teacher_id: UUID
    note: str
    visibility: BookingNoteVisibility
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
