from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.admin.schemas import (
    AdminDashboardSummaryRead,
    AdminStudentAccessGrantCreate,
    AdminStudentAccessGrantRead,
    AdminStudentAccessState,
    AdminStudentBatchGroupSet,
    AdminStudentCreate,
    AdminStudentPaymentCreate,
    AdminStudentPaymentRead,
    AdminStudentPaymentUpdate,
    AdminStudentRead,
    AdminTeacherAvailabilityGenerationResult,
    AdminTeacherCreate,
    AdminTeacherRead,
)
from app.modules.admin.service import AdminService
from app.modules.batch_groups.schemas import (
    BatchGroupRead,
    BatchGroupUpdate,
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
from app.modules.packages.schemas import PackageRead, PackageUpdate
from app.modules.schedules.schemas import (
    TeacherAvailabilityBlockCreate,
    TeacherAvailabilityRuleCreate,
    TeacherAvailabilityRuleRead,
    TeacherAvailabilityRuleUpdate,
    TeacherAvailabilitySlotBulkCreate,
    TeacherAvailabilitySlotCreate,
    TeacherAvailabilitySlotRead,
    TeacherAvailabilitySlotUpdate,
)
from app.modules.students.schemas import (
    StudentProgramChangeRead,
    StudentProgramSwitch,
    StudentUpdate,
)
from app.modules.teachers.schemas import TeacherUpdate
from app.modules.users.schemas import UserRead, UserUpdate
from app.shared.enums import BookingStatus, ClassSessionStatus, StudentProgramType, StudentStatus

router = APIRouter()
DatetimeQuery = Annotated[datetime | None, Query()]
ProgramTypeQuery = Annotated[StudentProgramType | None, Query()]
IsActiveQuery = Annotated[bool | None, Query()]
SearchQuery = Annotated[str | None, Query(max_length=150)]
StudentStatusQuery = Annotated[StudentStatus | None, Query()]
StudentAccessStateQuery = Annotated[AdminStudentAccessState | None, Query()]
ClassSessionStatusQuery = Annotated[ClassSessionStatus | None, Query()]
BookingStatusQuery = Annotated[BookingStatus | None, Query()]
TeacherIdQuery = Annotated[UUID | None, Query()]
DaysAheadQuery = Annotated[int, Query(ge=1, le=90)]


def normalize_query_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("/dashboard/summary", response_model=AdminDashboardSummaryRead)
async def get_dashboard_summary(
    session: DBSession,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
) -> AdminDashboardSummaryRead:
    try:
        return await AdminService(session).get_dashboard_summary(
            starts_from=normalize_query_datetime(starts_from),
            starts_to=normalize_query_datetime(starts_to),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/students", response_model=Page[AdminStudentRead])
async def list_students(
    session: DBSession,
    pagination: Pagination,
    q: SearchQuery = None,
    status: StudentStatusQuery = None,
    program_type: ProgramTypeQuery = None,
    access_state: StudentAccessStateQuery = None,
    batch_group_id: UUID | None = None,
) -> Page[AdminStudentRead]:
    return await AdminService(session).list_students(
        pagination,
        q=q,
        status=status,
        program_type=program_type,
        access_state=access_state,
        batch_group_id=batch_group_id,
    )


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    session: DBSession,
) -> UserRead:
    return await AdminService(session).update_user(user_id, user_in)


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
    q: SearchQuery = None,
    is_active: IsActiveQuery = None,
) -> Page[AdminTeacherRead]:
    return await AdminService(session).list_teachers(
        pagination,
        q=q,
        is_active=is_active,
    )


@router.get("/teachers/{teacher_id}", response_model=AdminTeacherRead)
async def get_teacher(
    teacher_id: UUID,
    session: DBSession,
) -> AdminTeacherRead:
    return await AdminService(session).get_teacher(teacher_id)


@router.patch("/teachers/{teacher_id}", response_model=AdminTeacherRead)
async def update_teacher(
    teacher_id: UUID,
    teacher_in: TeacherUpdate,
    session: DBSession,
) -> AdminTeacherRead:
    return await AdminService(session).update_teacher(teacher_id, teacher_in)


@router.post(
    "/teachers/{teacher_id}/availability/generate",
    response_model=AdminTeacherAvailabilityGenerationResult,
)
async def generate_teacher_availability_slots(
    teacher_id: UUID,
    session: DBSession,
    days_ahead: DaysAheadQuery = 14,
) -> AdminTeacherAvailabilityGenerationResult:
    result = await AdminService(session).generate_teacher_availability_slots(
        teacher_id,
        days_ahead=days_ahead,
    )
    return AdminTeacherAvailabilityGenerationResult(
        rules_checked=result.rules_checked,
        slots_created=result.slots_created,
        slots_cancelled=result.slots_cancelled,
        slots_skipped=result.slots_skipped,
    )


@router.get(
    "/teacher-availability/rules",
    response_model=Page[TeacherAvailabilityRuleRead],
)
async def list_teacher_availability_rules(
    session: DBSession,
    pagination: Pagination,
    teacher_id: TeacherIdQuery = None,
) -> Page[TeacherAvailabilityRuleRead]:
    return await AdminService(session).list_teacher_availability_rules(
        pagination,
        teacher_id=teacher_id,
    )


@router.post(
    "/teacher-availability/rules",
    response_model=TeacherAvailabilityRuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_rule(
    rule_in: TeacherAvailabilityRuleCreate,
    session: DBSession,
) -> TeacherAvailabilityRuleRead:
    return await AdminService(session).create_teacher_availability_rule(rule_in)


@router.get(
    "/teacher-availability/rules/{rule_id}",
    response_model=TeacherAvailabilityRuleRead,
)
async def get_teacher_availability_rule(
    rule_id: UUID,
    session: DBSession,
) -> TeacherAvailabilityRuleRead:
    return await AdminService(session).get_teacher_availability_rule(rule_id)


@router.patch(
    "/teacher-availability/rules/{rule_id}",
    response_model=TeacherAvailabilityRuleRead,
)
async def update_teacher_availability_rule(
    rule_id: UUID,
    rule_in: TeacherAvailabilityRuleUpdate,
    session: DBSession,
) -> TeacherAvailabilityRuleRead:
    return await AdminService(session).update_teacher_availability_rule(rule_id, rule_in)


@router.delete(
    "/teacher-availability/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_teacher_availability_rule(
    rule_id: UUID,
    session: DBSession,
) -> Response:
    await AdminService(session).delete_teacher_availability_rule(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/teacher-availability/slots",
    response_model=Page[TeacherAvailabilitySlotRead],
)
async def list_teacher_availability_slots(
    session: DBSession,
    pagination: Pagination,
    teacher_id: TeacherIdQuery = None,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
) -> Page[TeacherAvailabilitySlotRead]:
    return await AdminService(session).list_teacher_availability_slots(
        pagination,
        teacher_id=teacher_id,
        starts_from=normalize_query_datetime(starts_from),
        starts_to=normalize_query_datetime(starts_to),
    )


@router.post(
    "/teacher-availability/slots",
    response_model=TeacherAvailabilitySlotRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_slot(
    slot_in: TeacherAvailabilitySlotCreate,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await AdminService(session).create_teacher_availability_slot(slot_in)


@router.post(
    "/teacher-availability/slots/bulk",
    response_model=list[TeacherAvailabilitySlotRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_slots_bulk(
    slots_in: TeacherAvailabilitySlotBulkCreate,
    session: DBSession,
) -> list[TeacherAvailabilitySlotRead]:
    return await AdminService(session).create_teacher_availability_slots_bulk(slots_in)


@router.post(
    "/teacher-availability/blocks",
    response_model=TeacherAvailabilitySlotRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_availability_block(
    block_in: TeacherAvailabilityBlockCreate,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await AdminService(session).create_teacher_availability_block(block_in)


@router.get(
    "/teacher-availability/slots/{slot_id}",
    response_model=TeacherAvailabilitySlotRead,
)
async def get_teacher_availability_slot(
    slot_id: UUID,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await AdminService(session).get_teacher_availability_slot(slot_id)


@router.patch(
    "/teacher-availability/slots/{slot_id}",
    response_model=TeacherAvailabilitySlotRead,
)
async def update_teacher_availability_slot(
    slot_id: UUID,
    slot_in: TeacherAvailabilitySlotUpdate,
    session: DBSession,
) -> TeacherAvailabilitySlotRead:
    return await AdminService(session).update_teacher_availability_slot(slot_id, slot_in)


@router.delete(
    "/teacher-availability/slots/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_teacher_availability_slot(
    slot_id: UUID,
    session: DBSession,
) -> Response:
    await AdminService(session).delete_teacher_availability_slot(slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.patch("/students/{student_id}", response_model=AdminStudentRead)
async def update_student(
    student_id: UUID,
    student_in: StudentUpdate,
    session: DBSession,
) -> AdminStudentRead:
    return await AdminService(session).update_student(student_id, student_in)


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


@router.patch(
    "/students/{student_id}/payments/{payment_id}",
    response_model=AdminStudentPaymentRead,
)
async def update_student_payment(
    student_id: UUID,
    payment_id: UUID,
    payment_in: AdminStudentPaymentUpdate,
    session: DBSession,
) -> AdminStudentPaymentRead:
    return await AdminService(session).update_student_payment(
        student_id,
        payment_id,
        payment_in,
    )


@router.delete(
    "/students/{student_id}/payments/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_student_payment(
    student_id: UUID,
    payment_id: UUID,
    session: DBSession,
) -> Response:
    await AdminService(session).delete_student_payment(student_id, payment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.patch("/batch-groups/{batch_group_id}", response_model=BatchGroupRead)
async def update_batch_group(
    batch_group_id: UUID,
    batch_group_in: BatchGroupUpdate,
    session: DBSession,
) -> BatchGroupRead:
    return await AdminService(session).update_batch_group(batch_group_id, batch_group_in)


@router.post("/batch-groups/{batch_group_id}/void", response_model=BatchGroupRead)
async def void_batch_group(
    batch_group_id: UUID,
    session: DBSession,
) -> BatchGroupRead:
    return await AdminService(session).void_batch_group(batch_group_id)


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


@router.patch("/packages/{package_id}", response_model=PackageRead)
async def update_package(
    package_id: UUID,
    package_in: PackageUpdate,
    session: DBSession,
) -> PackageRead:
    return await AdminService(session).update_package(package_id, package_in)


@router.post("/packages/{package_id}/void", response_model=PackageRead)
async def void_package(
    package_id: UUID,
    session: DBSession,
) -> PackageRead:
    return await AdminService(session).void_package(package_id)


@router.get("/classes", response_model=Page[ClassSessionRead])
async def list_classes(
    session: DBSession,
    pagination: Pagination,
    program_type: ProgramTypeQuery = None,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
    status: ClassSessionStatusQuery = None,
    teacher_id: UUID | None = None,
    batch_group_id: UUID | None = None,
) -> Page[ClassSessionRead]:
    return await AdminService(session).list_class_sessions(
        pagination,
        program_type=program_type,
        starts_from=normalize_query_datetime(starts_from),
        starts_to=normalize_query_datetime(starts_to),
        status=status,
        teacher_id=teacher_id,
        batch_group_id=batch_group_id,
    )


@router.get("/classes/{class_session_id}", response_model=ClassSessionRead)
async def get_class_session(
    class_session_id: UUID,
    session: DBSession,
) -> ClassSessionRead:
    return await AdminService(session).get_class_session(class_session_id)


@router.post("/classes/{class_session_id}/cancel", response_model=ClassSessionRead)
async def cancel_class_session(
    class_session_id: UUID,
    cancel_in: BookingActionRequest,
    session: DBSession,
) -> ClassSessionRead:
    return await AdminService(session).cancel_class_session(class_session_id, cancel_in)


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
    return await AdminService(session).list_bookings(
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
