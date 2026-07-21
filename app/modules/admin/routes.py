from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.admin.schemas import (
    AdminStudentAccessGrantCreate,
    AdminStudentAccessGrantRead,
    AdminStudentBatchGroupSet,
    AdminStudentCreate,
    AdminStudentPaymentCreate,
    AdminStudentPaymentRead,
    AdminStudentRead,
    AdminTeacherCreate,
    AdminTeacherRead,
)
from app.modules.admin.service import AdminService
from app.modules.batch_groups.schemas import (
    BatchGroupRead,
    BatchSessionBulkGenerate,
    BatchSessionBulkGenerateResult,
    StudentBatchMembershipRead,
)
from app.modules.bookings.schemas import (
    AdminAddStudentToClass,
    BatchBookingReschedule,
    BookingActionRequest,
    BookingEventRead,
    BookingRead,
    ClassAttendanceMark,
    OneOnOneBookingReschedule,
)
from app.modules.classes.schemas import BatchClassSessionCreate, ClassSessionRead
from app.modules.packages.schemas import PackageRead
from app.modules.students.schemas import StudentProgramChangeRead, StudentProgramSwitch
from app.shared.enums import StudentProgramType

router = APIRouter()
DatetimeQuery = Annotated[datetime | None, Query()]
ProgramTypeQuery = Annotated[StudentProgramType | None, Query()]
IsActiveQuery = Annotated[bool | None, Query()]


def normalize_query_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("/students", response_model=Page[AdminStudentRead])
async def list_students(
    session: DBSession,
    pagination: Pagination,
) -> Page[AdminStudentRead]:
    return await AdminService(session).list_students(pagination)


@router.post("/teachers", response_model=AdminTeacherRead, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    teacher_in: AdminTeacherCreate,
    session: DBSession,
) -> AdminTeacherRead:
    user, teacher = await AdminService(session).create_teacher(teacher_in)
    return AdminTeacherRead(user=user, teacher=teacher)


@router.get("/teachers", response_model=Page[AdminTeacherRead])
async def list_teachers(
    session: DBSession,
    pagination: Pagination,
) -> Page[AdminTeacherRead]:
    return await AdminService(session).list_teachers(pagination)


@router.get("/teachers/{teacher_id}", response_model=AdminTeacherRead)
async def get_teacher(
    teacher_id: UUID,
    session: DBSession,
) -> AdminTeacherRead:
    return await AdminService(session).get_teacher(teacher_id)


@router.post("/students", response_model=AdminStudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(
    student_in: AdminStudentCreate,
    session: DBSession,
) -> AdminStudentRead:
    user, student = await AdminService(session).create_student(student_in)
    return AdminStudentRead(user=user, student=student)


@router.get("/students/{student_id}", response_model=AdminStudentRead)
async def get_student(
    student_id: UUID,
    session: DBSession,
) -> AdminStudentRead:
    return await AdminService(session).get_student(student_id)


@router.get("/students/{student_id}/payments", response_model=Page[AdminStudentPaymentRead])
async def list_student_payments(
    student_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[AdminStudentPaymentRead]:
    return await AdminService(session).list_student_payments(student_id, pagination)


@router.post(
    "/students/{student_id}/payments",
    response_model=AdminStudentPaymentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_student_payment(
    student_id: UUID,
    payment_in: AdminStudentPaymentCreate,
    session: DBSession,
) -> AdminStudentPaymentRead:
    return await AdminService(session).create_student_payment(student_id, payment_in)


@router.get(
    "/students/{student_id}/access-grants",
    response_model=Page[AdminStudentAccessGrantRead],
)
async def list_student_access_grants(
    student_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[AdminStudentAccessGrantRead]:
    return await AdminService(session).list_student_access_grants(student_id, pagination)


@router.post(
    "/students/{student_id}/access-grants",
    response_model=AdminStudentAccessGrantRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_student_access_grant(
    student_id: UUID,
    grant_in: AdminStudentAccessGrantCreate,
    session: DBSession,
) -> AdminStudentAccessGrantRead:
    return await AdminService(session).create_student_access_grant(student_id, grant_in)


@router.post(
    "/students/{student_id}/program-switch",
    response_model=StudentProgramChangeRead,
)
async def switch_student_program(
    student_id: UUID,
    switch_in: StudentProgramSwitch,
    session: DBSession,
) -> StudentProgramChangeRead:
    return await AdminService(session).switch_student_program(student_id, switch_in)


@router.post(
    "/students/{student_id}/batch-group",
    response_model=StudentBatchMembershipRead,
)
async def set_student_batch_group(
    student_id: UUID,
    batch_group_in: AdminStudentBatchGroupSet,
    session: DBSession,
) -> StudentBatchMembershipRead:
    return await AdminService(session).set_student_batch_group(student_id, batch_group_in)


@router.get(
    "/students/{student_id}/batch-memberships",
    response_model=Page[StudentBatchMembershipRead],
)
async def list_student_batch_memberships(
    student_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[StudentBatchMembershipRead]:
    return await AdminService(session).list_student_batch_memberships(student_id, pagination)


@router.get("/batch-groups", response_model=Page[BatchGroupRead])
async def list_batch_groups(
    session: DBSession,
    pagination: Pagination,
    is_active: IsActiveQuery = None,
) -> Page[BatchGroupRead]:
    return await AdminService(session).list_batch_groups(pagination, is_active=is_active)


@router.get("/batch-groups/{batch_group_id}", response_model=BatchGroupRead)
async def get_batch_group(
    batch_group_id: UUID,
    session: DBSession,
) -> BatchGroupRead:
    return await AdminService(session).get_batch_group(batch_group_id)


@router.get(
    "/batch-groups/{batch_group_id}/students",
    response_model=Page[StudentBatchMembershipRead],
)
async def list_batch_group_students(
    batch_group_id: UUID,
    session: DBSession,
    pagination: Pagination,
    is_active: IsActiveQuery = True,
) -> Page[StudentBatchMembershipRead]:
    return await AdminService(session).list_batch_group_students(
        batch_group_id=batch_group_id,
        pagination=pagination,
        is_active=is_active,
    )


@router.get("/packages", response_model=Page[PackageRead])
async def list_packages(
    session: DBSession,
    pagination: Pagination,
) -> Page[PackageRead]:
    return await AdminService(session).list_packages(pagination)


@router.get("/packages/{package_id}", response_model=PackageRead)
async def get_package(
    package_id: UUID,
    session: DBSession,
) -> PackageRead:
    return await AdminService(session).get_package(package_id)


@router.get("/classes", response_model=Page[ClassSessionRead])
async def list_classes(
    session: DBSession,
    pagination: Pagination,
    program_type: ProgramTypeQuery = None,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
) -> Page[ClassSessionRead]:
    return await AdminService(session).list_class_sessions(
        pagination,
        program_type=program_type,
        starts_from=normalize_query_datetime(starts_from),
        starts_to=normalize_query_datetime(starts_to),
    )


@router.get("/classes/{class_session_id}", response_model=ClassSessionRead)
async def get_class_session(
    class_session_id: UUID,
    session: DBSession,
) -> ClassSessionRead:
    return await AdminService(session).get_class_session(class_session_id)


@router.get("/bookings", response_model=Page[BookingRead])
async def list_bookings(
    session: DBSession,
    pagination: Pagination,
    student_id: UUID | None = None,
    class_session_id: UUID | None = None,
) -> Page[BookingRead]:
    return await AdminService(session).list_bookings(
        pagination,
        student_id=student_id,
        class_session_id=class_session_id,
    )


@router.get("/bookings/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: UUID,
    session: DBSession,
) -> BookingRead:
    return await AdminService(session).get_booking(booking_id)


@router.get("/bookings/{booking_id}/events", response_model=Page[BookingEventRead])
async def list_booking_events(
    booking_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[BookingEventRead]:
    return await AdminService(session).list_booking_events(booking_id, pagination)


@router.post(
    "/batch-groups/{batch_group_id}/sessions/generate",
    response_model=BatchSessionBulkGenerateResult,
)
async def generate_batch_sessions(
    batch_group_id: UUID,
    generation_in: BatchSessionBulkGenerate,
    session: DBSession,
) -> BatchSessionBulkGenerateResult:
    class_sessions = await AdminService(session).generate_batch_sessions(
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
    return await AdminService(session).create_batch_class_session(class_session_in)


@router.post("/classes/{class_session_id}/students", response_model=BookingRead)
async def add_student_to_class(
    class_session_id: UUID,
    add_in: AdminAddStudentToClass,
    session: DBSession,
) -> BookingRead:
    return await AdminService(session).add_student_to_class(class_session_id, add_in)


@router.post("/classes/{class_session_id}/attendance", response_model=list[BookingRead])
async def mark_class_attendance(
    class_session_id: UUID,
    attendance_in: ClassAttendanceMark,
    session: DBSession,
) -> list[BookingRead]:
    return await AdminService(session).mark_class_attendance(class_session_id, attendance_in)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: UUID,
    cancel_in: BookingActionRequest,
    session: DBSession,
) -> BookingRead:
    return await AdminService(session).cancel_booking(booking_id, cancel_in)


@router.post("/bookings/{booking_id}/reschedule/one-on-one", response_model=BookingRead)
async def reschedule_one_on_one_booking(
    booking_id: UUID,
    reschedule_in: OneOnOneBookingReschedule,
    session: DBSession,
) -> BookingRead:
    return await AdminService(session).reschedule_one_on_one_booking(
        booking_id,
        reschedule_in,
    )


@router.post("/bookings/{booking_id}/reschedule/batch", response_model=BookingRead)
async def reschedule_batch_booking(
    booking_id: UUID,
    reschedule_in: BatchBookingReschedule,
    session: DBSession,
) -> BookingRead:
    return await AdminService(session).reschedule_batch_booking(booking_id, reschedule_in)
