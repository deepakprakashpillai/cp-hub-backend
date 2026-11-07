from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.auth.dependencies import get_current_teacher
from app.modules.booking_notes.schemas import (
    BookingNoteCreate,
    BookingNoteRead,
    BookingNoteUpdate,
)
from app.modules.booking_notes.service import BookingNoteService
from app.modules.teachers.models import Teacher

router = APIRouter()
CurrentTeacher = Annotated[Teacher, Depends(get_current_teacher)]


@router.post(
    "/bookings/{booking_id}/notes",
    response_model=BookingNoteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_booking_note(
    booking_id: UUID,
    note_in: BookingNoteCreate,
    session: DBSession,
    teacher: CurrentTeacher,
) -> BookingNoteRead:
    return await BookingNoteService(session).create_booking_note(
        booking_id, note_in.model_copy(update={"teacher_id": teacher.id})
    )


@router.get(
    "/bookings/{booking_id}/notes",
    response_model=Page[BookingNoteRead],
)
async def list_booking_notes(
    booking_id: UUID,
    session: DBSession,
    pagination: Pagination,
    teacher: CurrentTeacher,
) -> Page[BookingNoteRead]:
    return await BookingNoteService(session).list_teacher_booking_notes(
        booking_id,
        teacher.id,
        pagination,
    )


@router.patch(
    "/booking-notes/{note_id}",
    response_model=BookingNoteRead,
)
async def update_booking_note(
    note_id: UUID,
    note_in: BookingNoteUpdate,
    session: DBSession,
    teacher: CurrentTeacher,
) -> BookingNoteRead:
    return await BookingNoteService(session).update_booking_note(
        note_id,
        teacher.id,
        note_in,
    )
