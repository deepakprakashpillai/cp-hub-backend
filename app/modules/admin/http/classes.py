from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.admin.http.types import (
    BookingStatusQuery,
    ClassSessionStatusQuery,
    DatetimeQuery,
    ProgramTypeQuery,
    SearchQuery,
    SortOrderQuery,
)
from app.modules.admin.schemas import (
    AdminBatchClassReschedule,
    AdminBatchClassRescheduleResult,
    AdminClassActivityRead,
    AdminClassRead,
    AdminClassRescheduleResult,
    AdminClassRosterBookingRead,
    SortOrder,
)
from app.modules.batch_groups.schemas import (
    BatchSessionBulkGenerate,
    BatchSessionBulkGenerateResult,
)
from app.modules.booking_notes.schemas import BookingNoteRead
from app.modules.bookings.schemas import (
    AdminAddStudentToClass,
    BatchBookingReschedule,
    BookingActionRequest,
    BookingEventRead,
    BookingRead,
    ClassAttendanceMark,
    OneOnOneBookingCreate,
    OneOnOneBookingReschedule,
)
from app.modules.classes.schemas import BatchClassSessionCreate, ClassSessionRead
from app.modules.read_models.services import (
    AdminClassService,
    AdminSchedulingService,
)

router = APIRouter()


def normalize_query_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("/classes", response_model=Page[AdminClassRead])
async def list_classes(
    session: DBSession,
    pagination: Pagination,
    program_type: ProgramTypeQuery = None,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
    status: ClassSessionStatusQuery = None,
    teacher_id: UUID | None = None,
    batch_group_id: UUID | None = None,
    sort_order: SortOrderQuery = SortOrder.ASC,
    q: SearchQuery = None,
) -> Page[AdminClassRead]:
    return await AdminClassService(session).list_class_sessions(
        pagination,
        program_type=program_type,
        starts_from=normalize_query_datetime(starts_from),
        starts_to=normalize_query_datetime(starts_to),
        status=status,
        teacher_id=teacher_id,
        batch_group_id=batch_group_id,
        sort_order=sort_order,
        q=q,
    )


@router.get("/classes/{class_session_id}", response_model=AdminClassRead)
async def get_class_session(
    class_session_id: UUID,
    session: DBSession,
) -> AdminClassRead:
    return await AdminClassService(session).get_class_session(class_session_id)


@router.post("/classes/{class_session_id}/cancel", response_model=AdminClassRead)
async def cancel_class_session(
    class_session_id: UUID,
    cancel_in: BookingActionRequest,
    session: DBSession,
) -> AdminClassRead:
    return await AdminClassService(session).cancel_class_session(class_session_id, cancel_in)


@router.get(
    "/classes/{class_session_id}/roster",
    response_model=Page[AdminClassRosterBookingRead],
)
async def list_class_roster(
    class_session_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[AdminClassRosterBookingRead]:
    return await AdminClassService(session).list_class_roster(class_session_id, pagination)


@router.get(
    "/classes/{class_session_id}/activity",
    response_model=Page[AdminClassActivityRead],
)
async def list_class_activity(
    class_session_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[AdminClassActivityRead]:
    return await AdminClassService(session).list_class_activity(class_session_id, pagination)


@router.get("/bookings", response_model=Page[BookingRead])
async def list_bookings(
    session: DBSession,
    pagination: Pagination,
    student_id: UUID | None = None,
    class_session_id: UUID | None = None,
    status: BookingStatusQuery = None,
    teacher_id: UUID | None = None,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
) -> Page[BookingRead]:
    return await AdminClassService(session).list_bookings(
        pagination,
        student_id=student_id,
        class_session_id=class_session_id,
        status=status,
        teacher_id=teacher_id,
        starts_from=normalize_query_datetime(starts_from),
        starts_to=normalize_query_datetime(starts_to),
    )


@router.get("/bookings/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: UUID,
    session: DBSession,
) -> BookingRead:
    return await AdminClassService(session).get_booking(booking_id)


@router.get("/bookings/{booking_id}/events", response_model=Page[BookingEventRead])
async def list_booking_events(
    booking_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[BookingEventRead]:
    return await AdminClassService(session).list_booking_events(booking_id, pagination)


@router.get("/bookings/{booking_id}/notes", response_model=Page[BookingNoteRead])
async def list_booking_notes(
    booking_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[BookingNoteRead]:
    return await AdminClassService(session).list_booking_notes(booking_id, pagination)


@router.post(
    "/batch-groups/{batch_group_id}/sessions/generate",
    response_model=BatchSessionBulkGenerateResult,
)
async def generate_batch_sessions(
    batch_group_id: UUID,
    generation_in: BatchSessionBulkGenerate,
    session: DBSession,
) -> BatchSessionBulkGenerateResult:
    class_sessions = await AdminSchedulingService(session).generate_batch_sessions(
        batch_group_id,
        generation_in,
    )
    return BatchSessionBulkGenerateResult(
        created_count=len(class_sessions),
        class_sessions=class_sessions,
    )


@router.post(
    "/classes/batch",
    response_model=ClassSessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_batch_class_session(
    class_session_in: BatchClassSessionCreate,
    session: DBSession,
) -> ClassSessionRead:
    return await AdminClassService(session).create_batch_class_session(class_session_in)


@router.post(
    "/bookings/one-on-one",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_one_on_one_booking(
    booking_in: OneOnOneBookingCreate,
    session: DBSession,
) -> BookingRead:
    return await AdminClassService(session).create_one_on_one_booking(booking_in)


@router.post("/classes/{class_session_id}/students", response_model=BookingRead)
async def add_student_to_class(
    class_session_id: UUID,
    add_in: AdminAddStudentToClass,
    session: DBSession,
) -> BookingRead:
    return await AdminClassService(session).add_student_to_class(class_session_id, add_in)


@router.post("/classes/{class_session_id}/attendance", response_model=list[BookingRead])
async def mark_class_attendance(
    class_session_id: UUID,
    attendance_in: ClassAttendanceMark,
    session: DBSession,
) -> list[BookingRead]:
    return await AdminClassService(session).mark_class_attendance(class_session_id, attendance_in)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: UUID,
    cancel_in: BookingActionRequest,
    session: DBSession,
) -> BookingRead:
    return await AdminClassService(session).cancel_booking(booking_id, cancel_in)


@router.post("/bookings/{booking_id}/reschedule/one-on-one", response_model=BookingRead)
async def reschedule_one_on_one_booking(
    booking_id: UUID,
    reschedule_in: OneOnOneBookingReschedule,
    session: DBSession,
) -> BookingRead:
    return await AdminClassService(session).reschedule_one_on_one_booking(
        booking_id,
        reschedule_in,
    )


@router.post("/bookings/{booking_id}/reschedule/batch", response_model=BookingRead)
async def reschedule_batch_booking(
    booking_id: UUID,
    reschedule_in: BatchBookingReschedule,
    session: DBSession,
) -> BookingRead:
    return await AdminClassService(session).reschedule_batch_booking(booking_id, reschedule_in)


@router.post(
    "/classes/{class_session_id}/reschedule/one-on-one",
    response_model=AdminClassRescheduleResult,
)
async def reschedule_one_on_one_class(
    class_session_id: UUID,
    reschedule_in: OneOnOneBookingReschedule,
    session: DBSession,
) -> AdminClassRescheduleResult:
    return await AdminClassService(session).reschedule_one_on_one_class(
        class_session_id,
        reschedule_in,
    )


@router.post(
    "/classes/{class_session_id}/reschedule/batch",
    response_model=AdminBatchClassRescheduleResult,
)
async def reschedule_batch_class(
    class_session_id: UUID,
    reschedule_in: AdminBatchClassReschedule,
    session: DBSession,
) -> AdminBatchClassRescheduleResult:
    return await AdminClassService(session).reschedule_batch_class(
        class_session_id,
        reschedule_in,
    )
