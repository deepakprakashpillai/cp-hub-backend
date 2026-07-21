from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession
from app.modules.bookings.schemas import (
    BatchBookingCreate,
    BatchBookingReschedule,
    BookingActionRequest,
    BookingEventRead,
    BookingRead,
    OneOnOneBookingCreate,
    OneOnOneBookingReschedule,
)
from app.modules.bookings.service import BookingService

router = APIRouter()


@router.get("", response_model=list[BookingRead])
async def list_bookings(
    session: DBSession,
    student_id: UUID | None = None,
    class_session_id: UUID | None = None,
) -> list[BookingRead]:
    return await BookingService(session).list_bookings(
        student_id=student_id,
        class_session_id=class_session_id,
    )


@router.post(
    "/one-on-one",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_one_on_one_booking(
    booking_in: OneOnOneBookingCreate,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).create_one_on_one_booking(booking_in)


@router.post("/batch", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_batch_booking(
    booking_in: BatchBookingCreate,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).create_batch_booking(booking_in)


@router.post("/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: UUID,
    cancel_in: BookingActionRequest,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).cancel_booking(booking_id, cancel_in)


@router.post("/{booking_id}/admin-cancel", response_model=BookingRead)
async def admin_cancel_booking(
    booking_id: UUID,
    cancel_in: BookingActionRequest,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).admin_cancel_booking(booking_id, cancel_in)


@router.post("/{booking_id}/reschedule/one-on-one", response_model=BookingRead)
async def reschedule_one_on_one_booking(
    booking_id: UUID,
    reschedule_in: OneOnOneBookingReschedule,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).reschedule_one_on_one_booking(
        booking_id,
        reschedule_in,
    )


@router.post("/{booking_id}/admin-reschedule/one-on-one", response_model=BookingRead)
async def admin_reschedule_one_on_one_booking(
    booking_id: UUID,
    reschedule_in: OneOnOneBookingReschedule,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).admin_reschedule_one_on_one_booking(
        booking_id,
        reschedule_in,
    )


@router.post("/{booking_id}/reschedule/batch", response_model=BookingRead)
async def reschedule_batch_booking(
    booking_id: UUID,
    reschedule_in: BatchBookingReschedule,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).reschedule_batch_booking(
        booking_id,
        reschedule_in,
    )


@router.post("/{booking_id}/admin-reschedule/batch", response_model=BookingRead)
async def admin_reschedule_batch_booking(
    booking_id: UUID,
    reschedule_in: BatchBookingReschedule,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).admin_reschedule_batch_booking(
        booking_id,
        reschedule_in,
    )


@router.get("/{booking_id}/events", response_model=list[BookingEventRead])
async def list_booking_events(
    booking_id: UUID,
    session: DBSession,
) -> list[BookingEventRead]:
    return await BookingService(session).list_booking_events(booking_id)


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: UUID,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).get_booking(booking_id)
