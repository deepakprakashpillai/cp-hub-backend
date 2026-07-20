from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession
from app.modules.bookings.schemas import BatchBookingCreate, BookingRead, OneOnOneBookingCreate
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


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: UUID,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).get_booking(booking_id)
