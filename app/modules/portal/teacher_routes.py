from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.auth.dependencies import get_current_teacher
from app.modules.batch_schedule_days.schemas import (
    BatchDayOptionUpdate,
)
from app.modules.batch_schedule_days.service import (
    BatchScheduleOptionService,
)
from app.modules.bookings.schemas import (
    BookingActionRequest,
    BookingRead,
    ClassAttendanceMark,
)
from app.modules.bookings.service import (
    BookingAttendanceService,
    BookingCancellationService,
)
from app.modules.classes.models import ClassSession
from app.modules.classes.service import ClassSessionService
from app.modules.portal.schemas import (
    TeacherAvailabilityBlockSelfCreate,
    TeacherAvailabilityRuleSelfCreate,
    TeacherAvailabilitySlotSelfBulkCreate,
    TeacherAvailabilitySlotSelfCreate,
    TeacherClassCancel,
    TeacherClassScheduleUpdate,
    TeacherClassSessionRead,
)
from app.modules.read_models.schemas import (
    AdminClassRead,
    AdminClassRosterBookingRead,
    AdminStudentRead,
    AdminTeacherRead,
)
from app.modules.read_models.services import AdminAccountWorkflow, AdminClassService
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
from app.modules.schedules.service import ScheduleService
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherUpdate
from app.modules.teachers.workflows import TeacherLifecycleWorkflow
from app.shared.enums import (
    ClassSessionStatus,
    SortOrder,
    StudentProgramType,
)
from app.shared.utils import utc_now

teacher_router = APIRouter()
CurrentTeacher = Annotated[Teacher, Depends(get_current_teacher)]
DateQuery = Annotated[date | None, Query()]
DatetimeQuery = Annotated[datetime | None, Query()]


def _forbidden(detail: str = "You do not have access to this resource") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _teacher_class(session: DBSession, teacher: Teacher, class_id: UUID) -> ClassSession:
    class_session = await ClassSessionService(session).get_class_session(class_id)
    if class_session.teacher_id != teacher.id:
        raise _forbidden()
    return class_session


async def _teacher_rule(session: DBSession, teacher: Teacher, rule_id: UUID) -> None:
    rule = await ScheduleService(session).get_teacher_availability_rule(rule_id)
    if rule.teacher_id != teacher.id:
        raise _forbidden()


async def _teacher_slot(session: DBSession, teacher: Teacher, slot_id: UUID) -> None:
    slot = await ScheduleService(session).get_teacher_availability_slot(slot_id)
    if slot.teacher_id != teacher.id:
        raise _forbidden()


def _teacher_class_read(class_session: AdminClassRead) -> TeacherClassSessionRead:
    values = class_session.model_dump()
    values["booking_status_counts"] = values["booking_counts"]
    return TeacherClassSessionRead.model_validate(values)


async def get_my_teacher_profile(session: DBSession, teacher: CurrentTeacher) -> AdminTeacherRead:
    return await AdminAccountWorkflow(session).get_teacher(teacher.id)


async def update_my_teacher_profile(
    teacher_in: TeacherUpdate, session: DBSession, teacher: CurrentTeacher
) -> AdminTeacherRead:
    if "is_active" in teacher_in.model_fields_set:
        raise _forbidden("Teachers cannot change their account status")
    await TeacherLifecycleWorkflow(session).update_teacher(teacher.id, teacher_in)
    return await AdminAccountWorkflow(session).get_teacher(teacher.id)


async def list_my_classes(
    session: DBSession,
    pagination: Pagination,
    teacher: CurrentTeacher,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
    program_type: StudentProgramType | None = None,
    status: ClassSessionStatus | None = None,
    sort_order: SortOrder = SortOrder.ASC,
) -> Page[TeacherClassSessionRead]:
    page = await AdminClassService(session).list_class_sessions(
        pagination,
        teacher_id=teacher.id,
        starts_from=_normalize_datetime(starts_from),
        starts_to=_normalize_datetime(starts_to),
        program_type=program_type,
        status=status,
        sort_order=sort_order,
    )
    return Page(
        items=[_teacher_class_read(item) for item in page.items],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
    )


async def get_my_class(
    class_session_id: UUID, session: DBSession, teacher: CurrentTeacher
) -> TeacherClassSessionRead:
    await _teacher_class(session, teacher, class_session_id)
    return _teacher_class_read(await AdminClassService(session).get_class_session(class_session_id))


async def get_my_class_roster(
    class_session_id: UUID, session: DBSession, pagination: Pagination, teacher: CurrentTeacher
) -> Page[AdminClassRosterBookingRead]:
    await _teacher_class(session, teacher, class_session_id)
    return await AdminClassService(session).list_class_roster(class_session_id, pagination)


async def mark_my_class_attendance(
    class_session_id: UUID,
    attendance_in: ClassAttendanceMark,
    session: DBSession,
    teacher: CurrentTeacher,
) -> list[BookingRead]:
    await _teacher_class(session, teacher, class_session_id)
    return await BookingAttendanceService(session).mark_class_attendance(
        class_session_id,
        attendance_in.model_copy(update={"actor_user_id": teacher.user_id}),
    )


async def update_my_batch_class_schedule(
    class_session_id: UUID,
    schedule_in: TeacherClassScheduleUpdate,
    session: DBSession,
    teacher: CurrentTeacher,
) -> TeacherClassSessionRead:
    class_session = await _teacher_class(session, teacher, class_session_id)
    if (
        class_session.program_type != StudentProgramType.BATCH
        or class_session.batch_schedule_day_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Class session is not a batch schedule-day option",
        )
    if class_session.status != ClassSessionStatus.SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only scheduled class sessions can be updated",
        )
    now = utc_now()
    if class_session.starts_at <= now or schedule_in.starts_at <= now:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Started class sessions cannot be rescheduled",
        )
    await BatchScheduleOptionService(session).update_option(
        class_session.batch_schedule_day_id,
        class_session.id,
        BatchDayOptionUpdate(
            starts_at=schedule_in.starts_at,
            ends_at=schedule_in.ends_at,
            reason=schedule_in.reason,
            actor_user_id=teacher.user_id,
        ),
        event_source="teacher",
    )
    return _teacher_class_read(await AdminClassService(session).get_class_session(class_session_id))


async def cancel_my_batch_class(
    class_session_id: UUID,
    cancel_in: TeacherClassCancel,
    session: DBSession,
    teacher: CurrentTeacher,
) -> TeacherClassSessionRead:
    class_session = await _teacher_class(session, teacher, class_session_id)
    if (
        class_session.program_type != StudentProgramType.BATCH
        or class_session.batch_schedule_day_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Class session is not a batch schedule-day option",
        )
    await BookingCancellationService(session).teacher_cancel_batch_class_session(
        class_session.id,
        BookingActionRequest(actor_user_id=teacher.user_id, reason=cancel_in.reason),
    )
    return _teacher_class_read(await AdminClassService(session).get_class_session(class_session_id))


async def list_my_assigned_students(
    session: DBSession, pagination: Pagination, teacher: CurrentTeacher
) -> Page[AdminStudentRead]:
    return await AdminAccountWorkflow(session).list_students(
        pagination,
        assigned_teacher_id=teacher.id,
    )


async def list_my_availability_rules(
    session: DBSession, pagination: Pagination, teacher: CurrentTeacher
) -> Page[TeacherAvailabilityRuleRead]:
    return await ScheduleService(session).list_teacher_availability_rules(pagination, teacher.id)


async def create_my_availability_rule(
    rule_in: TeacherAvailabilityRuleSelfCreate, session: DBSession, teacher: CurrentTeacher
) -> TeacherAvailabilityRuleRead:
    return await ScheduleService(session).create_teacher_availability_rule(
        TeacherAvailabilityRuleCreate(teacher_id=teacher.id, **rule_in.model_dump())
    )


async def update_my_availability_rule(
    rule_id: UUID,
    rule_in: TeacherAvailabilityRuleUpdate,
    session: DBSession,
    teacher: CurrentTeacher,
) -> TeacherAvailabilityRuleRead:
    await _teacher_rule(session, teacher, rule_id)
    return await ScheduleService(session).update_teacher_availability_rule(rule_id, rule_in)


async def delete_my_availability_rule(
    rule_id: UUID, session: DBSession, teacher: CurrentTeacher
) -> Response:
    await _teacher_rule(session, teacher, rule_id)
    await ScheduleService(session).delete_teacher_availability_rule(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def list_my_availability_slots(
    session: DBSession,
    pagination: Pagination,
    teacher: CurrentTeacher,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
) -> Page[TeacherAvailabilitySlotRead]:
    return await ScheduleService(session).list_teacher_availability_slots(
        pagination,
        teacher_id=teacher.id,
        starts_from=_normalize_datetime(starts_from),
        starts_to=_normalize_datetime(starts_to),
    )


async def create_my_availability_slot(
    slot_in: TeacherAvailabilitySlotSelfCreate, session: DBSession, teacher: CurrentTeacher
) -> TeacherAvailabilitySlotRead:
    return await ScheduleService(session).create_teacher_availability_slot(
        TeacherAvailabilitySlotCreate(teacher_id=teacher.id, **slot_in.model_dump())
    )


async def create_my_availability_slots_bulk(
    slots_in: TeacherAvailabilitySlotSelfBulkCreate, session: DBSession, teacher: CurrentTeacher
) -> list[TeacherAvailabilitySlotRead]:
    slots = [
        TeacherAvailabilitySlotCreate(teacher_id=teacher.id, **slot.model_dump())
        for slot in slots_in.slots
    ]
    return await ScheduleService(session).create_teacher_availability_slots_bulk(
        TeacherAvailabilitySlotBulkCreate(slots=slots)
    )


async def update_my_availability_slot(
    slot_id: UUID,
    slot_in: TeacherAvailabilitySlotUpdate,
    session: DBSession,
    teacher: CurrentTeacher,
) -> TeacherAvailabilitySlotRead:
    await _teacher_slot(session, teacher, slot_id)
    return await ScheduleService(session).update_teacher_availability_slot(slot_id, slot_in)


async def delete_my_availability_slot(
    slot_id: UUID, session: DBSession, teacher: CurrentTeacher
) -> Response:
    await _teacher_slot(session, teacher, slot_id)
    await ScheduleService(session).delete_teacher_availability_slot(slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def create_my_availability_block(
    block_in: TeacherAvailabilityBlockSelfCreate, session: DBSession, teacher: CurrentTeacher
) -> TeacherAvailabilitySlotRead:
    return await ScheduleService(session).create_teacher_availability_block(
        TeacherAvailabilityBlockCreate(teacher_id=teacher.id, **block_in.model_dump())
    )


async def generate_my_availability_slots(
    session: DBSession, teacher: CurrentTeacher, days_ahead: int = Query(default=14, ge=1, le=90)
) -> dict[str, int]:
    result = await ScheduleService(session).generate_teacher_availability_slots(
        teacher.id, days_ahead=days_ahead
    )
    return {
        "rules_checked": result.rules_checked,
        "slots_created": result.slots_created,
        "slots_cancelled": result.slots_cancelled,
        "slots_skipped": result.slots_skipped,
    }


teacher_router.add_api_route("/me", get_my_teacher_profile, methods=["GET"])
teacher_router.add_api_route("/me", update_my_teacher_profile, methods=["PATCH"])
teacher_router.add_api_route("/me/classes", list_my_classes, methods=["GET"])
teacher_router.add_api_route("/me/classes/{class_session_id}", get_my_class, methods=["GET"])
teacher_router.add_api_route(
    "/me/classes/{class_session_id}/roster", get_my_class_roster, methods=["GET"]
)
teacher_router.add_api_route(
    "/me/classes/{class_session_id}/attendance",
    mark_my_class_attendance,
    methods=["POST"],
)
teacher_router.add_api_route(
    "/me/classes/{class_session_id}/schedule",
    update_my_batch_class_schedule,
    methods=["PATCH"],
)
teacher_router.add_api_route(
    "/me/classes/{class_session_id}/cancel",
    cancel_my_batch_class,
    methods=["POST"],
)
teacher_router.add_api_route("/me/students", list_my_assigned_students, methods=["GET"])
teacher_router.add_api_route("/me/availability/rules", list_my_availability_rules, methods=["GET"])
teacher_router.add_api_route(
    "/me/availability/rules",
    create_my_availability_rule,
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
)
teacher_router.add_api_route(
    "/me/availability/rules/{rule_id}",
    update_my_availability_rule,
    methods=["PATCH"],
)
teacher_router.add_api_route(
    "/me/availability/rules/{rule_id}",
    delete_my_availability_rule,
    methods=["DELETE"],
    status_code=status.HTTP_204_NO_CONTENT,
)
teacher_router.add_api_route("/me/availability/slots", list_my_availability_slots, methods=["GET"])
teacher_router.add_api_route(
    "/me/availability/slots",
    create_my_availability_slot,
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
)
teacher_router.add_api_route(
    "/me/availability/slots/bulk",
    create_my_availability_slots_bulk,
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
)
teacher_router.add_api_route(
    "/me/availability/slots/{slot_id}",
    update_my_availability_slot,
    methods=["PATCH"],
)
teacher_router.add_api_route(
    "/me/availability/slots/{slot_id}",
    delete_my_availability_slot,
    methods=["DELETE"],
    status_code=status.HTTP_204_NO_CONTENT,
)
teacher_router.add_api_route(
    "/me/availability/blocks",
    create_my_availability_block,
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
)
teacher_router.add_api_route(
    "/me/availability/generate",
    generate_my_availability_slots,
    methods=["POST"],
)
