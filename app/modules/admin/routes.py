from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession
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
    BatchSessionBulkGenerate,
    BatchSessionBulkGenerateResult,
    StudentBatchMembershipRead,
)
from app.modules.bookings.schemas import (
    AdminAddStudentToClass,
    BatchBookingReschedule,
    BookingActionRequest,
    BookingRead,
    ClassAttendanceMark,
    OneOnOneBookingReschedule,
)
from app.modules.classes.schemas import BatchClassSessionCreate, ClassSessionRead
from app.modules.students.schemas import StudentProgramChangeRead, StudentProgramSwitch

router = APIRouter()


@router.post("/teachers", response_model=AdminTeacherRead, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    teacher_in: AdminTeacherCreate,
    session: DBSession,
) -> AdminTeacherRead:
    user, teacher = await AdminService(session).create_teacher(teacher_in)
    return AdminTeacherRead(user=user, teacher=teacher)


@router.post("/students", response_model=AdminStudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(
    student_in: AdminStudentCreate,
    session: DBSession,
) -> AdminStudentRead:
    user, student = await AdminService(session).create_student(student_in)
    return AdminStudentRead(user=user, student=student)


@router.get("/students/{student_id}/payments", response_model=list[AdminStudentPaymentRead])
async def list_student_payments(
    student_id: UUID,
    session: DBSession,
) -> list[AdminStudentPaymentRead]:
    return await AdminService(session).list_student_payments(student_id)


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
    response_model=list[AdminStudentAccessGrantRead],
)
async def list_student_access_grants(
    student_id: UUID,
    session: DBSession,
) -> list[AdminStudentAccessGrantRead]:
    return await AdminService(session).list_student_access_grants(student_id)


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
    response_model=list[StudentBatchMembershipRead],
)
async def list_student_batch_memberships(
    student_id: UUID,
    session: DBSession,
) -> list[StudentBatchMembershipRead]:
    return await AdminService(session).list_student_batch_memberships(student_id)


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
