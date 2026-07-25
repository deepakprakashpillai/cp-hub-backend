from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.booking_notes.schemas import (
    BookingNoteCreate,
    BookingNoteRead,
    BookingNoteUpdate,
)
from app.modules.booking_notes.service import BookingNoteService

router = APIRouter()


@router.post(
    "/bookings/{booking_id}/notes",
    response_model=BookingNoteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_booking_note(
    booking_id: UUID,
    note_in: BookingNoteCreate,
    session: DBSession,
) -> BookingNoteRead:
    return await BookingNoteService(session).create_booking_note(booking_id, note_in)


@router.get(
    "/bookings/{booking_id}/notes",
    response_model=Page[BookingNoteRead],
)
async def list_booking_notes(
    booking_id: UUID,
    teacher_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[BookingNoteRead]:
    return await BookingNoteService(session).list_teacher_booking_notes(
        booking_id,
        teacher_id,
        pagination,
    )


@router.patch(
    "/booking-notes/{note_id}",
    response_model=BookingNoteRead,
)
async def update_booking_note(
    note_id: UUID,
    teacher_id: UUID,
    note_in: BookingNoteUpdate,
    session: DBSession,
) -> BookingNoteRead:
    return await BookingNoteService(session).update_booking_note(
        note_id,
        teacher_id,
        note_in,
    )
