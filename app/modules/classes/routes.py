from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import DBSession
from app.modules.bookings.schemas import AdminAddStudentToClass, BookingRead, ClassAttendanceMark
from app.modules.bookings.service import BookingService
from app.modules.classes.schemas import BatchClassSessionCreate, ClassSessionRead
from app.modules.classes.service import ClassSessionService
from app.shared.enums import StudentProgramType

router = APIRouter()
DatetimeQuery = Annotated[datetime | None, Query()]
ProgramTypeQuery = Annotated[StudentProgramType | None, Query()]


def normalize_query_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("", response_model=list[ClassSessionRead])
async def list_classes(
    session: DBSession,
    program_type: ProgramTypeQuery = None,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
) -> list[ClassSessionRead]:
    return await ClassSessionService(session).list_class_sessions(
        program_type=program_type,
        starts_from=normalize_query_datetime(starts_from),
        starts_to=normalize_query_datetime(starts_to),
    )


@router.post("/batch", response_model=ClassSessionRead, status_code=status.HTTP_201_CREATED)
async def create_batch_class_session(
    class_session_in: BatchClassSessionCreate,
    session: DBSession,
) -> ClassSessionRead:
    return await ClassSessionService(session).create_batch_class_session(class_session_in)


@router.post("/{class_session_id}/attendance", response_model=list[BookingRead])
async def mark_class_attendance(
    class_session_id: UUID,
    attendance_in: ClassAttendanceMark,
    session: DBSession,
) -> list[BookingRead]:
    return await BookingService(session).mark_class_attendance(class_session_id, attendance_in)


@router.post("/{class_session_id}/admin-add-student", response_model=BookingRead)
async def admin_add_student_to_class(
    class_session_id: UUID,
    add_in: AdminAddStudentToClass,
    session: DBSession,
) -> BookingRead:
    return await BookingService(session).admin_add_student_to_class(class_session_id, add_in)


@router.get("/{class_session_id}", response_model=ClassSessionRead)
async def get_class_session(
    class_session_id: UUID,
    session: DBSession,
) -> ClassSessionRead:
    return await ClassSessionService(session).get_class_session(class_session_id)
