from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.auth.dependencies import get_current_student
from app.modules.batch_schedule_days.schemas import (
    BatchDayAllocationResult,
)
from app.modules.batch_schedule_days.service import (
    BatchScheduleDayQueryService,
)
from app.modules.booking_notes.models import BookingNote
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    BatchBookingReschedule,
    BookingActionRequest,
    OneOnOneBookingCreate,
    OneOnOneBookingReschedule,
)
from app.modules.bookings.service import (
    BookingCancellationService,
    BookingCreationService,
    BookingQueryService,
    BookingRescheduleService,
)
from app.modules.classes.models import ClassSession
from app.modules.portal.schemas import (
    StudentBatchDayRead,
    StudentBatchDaySelection,
    StudentBookingRead,
    StudentClassSessionRead,
    StudentFeedbackRead,
    StudentOneOnOneBookingCreate,
    StudentTeacherSlotRead,
)
from app.modules.read_models.schemas import (
    AdminClassRead,
    AdminStudentRead,
)
from app.modules.read_models.services import AdminAccountWorkflow, AdminClassService
from app.modules.schedules.service import ScheduleService
from app.modules.student_access_grants.schemas import StudentAccessGrantRead
from app.modules.student_access_grants.service import StudentAccessGrantService
from app.modules.students.models import Student
from app.shared.enums import (
    AvailabilitySlotStatus,
    BookingNoteVisibility,
    BookingStatus,
    StudentProgramType,
)
from app.shared.utils import utc_now

student_router = APIRouter()
CurrentStudent = Annotated[Student, Depends(get_current_student)]
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


async def _student_booking(session: DBSession, student: Student, booking_id: UUID) -> Booking:
    booking = await BookingQueryService(session).get_booking(booking_id)
    if booking.student_id != student.id:
        raise _forbidden()
    return booking


async def _student_assigned_teacher_slot(
    session: DBSession,
    student: Student,
    slot_id: UUID,
) -> None:
    if student.program_type != StudentProgramType.ONE_ON_ONE or student.assigned_teacher_id is None:
        raise _forbidden("No one-on-one teacher is assigned to this account")
    slot = await ScheduleService(session).get_teacher_availability_slot(slot_id)
    if slot.teacher_id != student.assigned_teacher_id:
        raise _forbidden("This availability slot is not offered by your assigned teacher")


def _student_class_read(class_session: AdminClassRead) -> StudentClassSessionRead:
    return StudentClassSessionRead.model_validate(
        {
            **class_session.model_dump(),
            "teacher": class_session.teacher,
            "batch_group": class_session.batch_group,
        }
    )


async def _student_booking_read(session: DBSession, booking: Booking) -> StudentBookingRead:
    class_session = await AdminClassService(session).get_class_session(booking.class_session_id)
    return StudentBookingRead.model_validate(
        {**booking.__dict__, "class_session": _student_class_read(class_session)}
    )


async def get_my_student_profile(session: DBSession, student: CurrentStudent) -> AdminStudentRead:
    return await AdminAccountWorkflow(session).get_student(student.id)


async def list_my_bookings(
    session: DBSession,
    pagination: Pagination,
    student: CurrentStudent,
    status: BookingStatus | None = None,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
) -> Page[StudentBookingRead]:
    page = await BookingQueryService(session).list_bookings(
        pagination,
        student_id=student.id,
        status=status,
        starts_from=_normalize_datetime(starts_from),
        starts_to=_normalize_datetime(starts_to),
    )
    return Page(
        items=[await _student_booking_read(session, booking) for booking in page.items],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
    )


async def get_my_booking(
    booking_id: UUID, session: DBSession, student: CurrentStudent
) -> StudentBookingRead:
    return await _student_booking_read(
        session, await _student_booking(session, student, booking_id)
    )


async def list_my_access_grants(
    session: DBSession, pagination: Pagination, student: CurrentStudent
) -> Page[StudentAccessGrantRead]:
    return await StudentAccessGrantService(session).list_grants(pagination, student.id)


async def list_my_available_slots(
    session: DBSession,
    pagination: Pagination,
    student: CurrentStudent,
    starts_from: DatetimeQuery = None,
    starts_to: DatetimeQuery = None,
) -> Page[StudentTeacherSlotRead]:
    if student.assigned_teacher_id is None:
        return Page(items=[], total=0, page=pagination.page, page_size=pagination.page_size)
    page = await ScheduleService(session).list_teacher_availability_slots(
        pagination,
        teacher_id=student.assigned_teacher_id,
        starts_from=_normalize_datetime(starts_from) or utc_now(),
        starts_to=_normalize_datetime(starts_to),
        status=AvailabilitySlotStatus.AVAILABLE,
    )
    assigned_teacher = await AdminAccountWorkflow(session).get_teacher(student.assigned_teacher_id)
    teacher_summary = assigned_teacher.teacher
    teacher_user = assigned_teacher.user
    return Page(
        items=[
            StudentTeacherSlotRead.model_validate(
                {
                    **slot.__dict__,
                    "teacher": {
                        "id": teacher_summary.id,
                        "display_name": teacher_summary.display_name,
                        "full_name": teacher_user.full_name,
                        "profile_photo_url": teacher_summary.profile_photo_url,
                    },
                }
            )
            for slot in page.items
        ],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
    )


async def create_my_one_on_one_booking(
    booking_in: StudentOneOnOneBookingCreate, session: DBSession, student: CurrentStudent
) -> StudentBookingRead:
    await _student_assigned_teacher_slot(session, student, booking_in.teacher_availability_slot_id)
    booking = await BookingCreationService(session).create_one_on_one_booking(
        OneOnOneBookingCreate(
            student_id=student.id,
            teacher_availability_slot_id=booking_in.teacher_availability_slot_id,
        )
    )
    return await _student_booking_read(session, booking)


async def cancel_my_booking(
    booking_id: UUID, cancel_in: BookingActionRequest, session: DBSession, student: CurrentStudent
) -> StudentBookingRead:
    await _student_booking(session, student, booking_id)
    booking = await BookingCancellationService(session).cancel_booking(
        booking_id, cancel_in.model_copy(update={"actor_user_id": student.user_id})
    )
    return await _student_booking_read(session, booking)


async def reschedule_my_one_on_one_booking(
    booking_id: UUID,
    reschedule_in: OneOnOneBookingReschedule,
    session: DBSession,
    student: CurrentStudent,
) -> StudentBookingRead:
    await _student_booking(session, student, booking_id)
    await _student_assigned_teacher_slot(
        session,
        student,
        reschedule_in.teacher_availability_slot_id,
    )
    booking = await BookingRescheduleService(session).reschedule_one_on_one_booking(
        booking_id, reschedule_in.model_copy(update={"actor_user_id": student.user_id})
    )
    return await _student_booking_read(session, booking)


async def reschedule_my_batch_booking(
    booking_id: UUID,
    reschedule_in: BatchBookingReschedule,
    session: DBSession,
    student: CurrentStudent,
) -> StudentBookingRead:
    await _student_booking(session, student, booking_id)
    booking = await BookingRescheduleService(session).reschedule_batch_booking(
        booking_id, reschedule_in.model_copy(update={"actor_user_id": student.user_id})
    )
    return await _student_booking_read(session, booking)


async def list_my_batch_schedule_days(
    session: DBSession,
    pagination: Pagination,
    student: CurrentStudent,
    starts_from: DateQuery = None,
    starts_to: DateQuery = None,
) -> list[StudentBatchDayRead]:
    page = await BatchScheduleDayQueryService(session).list_student_days(
        student.id, pagination, starts_from=starts_from, starts_to=starts_to
    )
    return [
        StudentBatchDayRead(
            id=day.id,
            batch_group_id=day.batch_group_id,
            schedule_date=day.schedule_date,
            selected_class_session_id=day.selected_class_session_id,
            options=[
                {
                    "id": option.id,
                    "display_label": option.display_label,
                    "batch_slot": None,
                    "starts_at": option.starts_at,
                    "ends_at": option.ends_at,
                    "capacity": option.capacity,
                    "booked_count": option.active_booking_count,
                    "teacher": (
                        {
                            "id": option.teacher.id,
                            "display_name": option.teacher.display_name,
                            "full_name": option.teacher.full_name,
                            "profile_photo_url": None,
                        }
                        if option.teacher is not None
                        else None
                    ),
                }
                for option in day.options
            ],
        )
        for day in page.items
    ]


async def select_my_batch_day_option(
    day_id: UUID,
    selection_in: StudentBatchDaySelection,
    session: DBSession,
    student: CurrentStudent,
) -> BatchDayAllocationResult:
    if selection_in.class_session_id is None:
        booking = await session.scalar(
            select(Booking)
            .join(ClassSession, Booking.class_session_id == ClassSession.id)
            .where(
                Booking.student_id == student.id,
                Booking.status == BookingStatus.BOOKED,
                ClassSession.batch_schedule_day_id == day_id,
            )
        )
        if booking is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selection not found")
        cancelled = await BookingCancellationService(session).cancel_booking(
            booking.id,
            BookingActionRequest(
                actor_user_id=student.user_id,
                reason=selection_in.reason or "selection cleared by student",
            ),
        )
        return BatchDayAllocationResult(booking=cancelled)
    booking, moved_from = await BookingCreationService(session).select_batch_day_option(
        student_id=student.id,
        batch_schedule_day_id=day_id,
        class_session_id=selection_in.class_session_id,
        admin_override=False,
        actor_user_id=student.user_id,
        reason=selection_in.reason,
    )
    return BatchDayAllocationResult(booking=booking, moved_from_booking_id=moved_from)


async def list_my_feedbacks(
    session: DBSession, student: CurrentStudent
) -> list[StudentFeedbackRead]:
    notes = await session.scalars(
        select(BookingNote)
        .join(Booking, BookingNote.booking_id == Booking.id)
        .where(
            Booking.student_id == student.id,
            BookingNote.visibility == BookingNoteVisibility.STUDENT_VISIBLE,
        )
        .order_by(BookingNote.created_at.desc())
    )
    items: list[StudentFeedbackRead] = []
    for note in notes:
        class_session = await AdminClassService(session).get_class_session(note.class_session_id)
        items.append(
            StudentFeedbackRead.model_validate(
                {
                    **note.__dict__,
                    "teacher": class_session.teacher,
                    "class_session": _student_class_read(class_session),
                }
            )
        )
    return items


student_router.add_api_route("/me", get_my_student_profile, methods=["GET"])
student_router.add_api_route("/me/bookings", list_my_bookings, methods=["GET"])
student_router.add_api_route("/me/bookings/{booking_id}", get_my_booking, methods=["GET"])
student_router.add_api_route("/me/access-grants", list_my_access_grants, methods=["GET"])
student_router.add_api_route("/me/available-slots", list_my_available_slots, methods=["GET"])
student_router.add_api_route(
    "/me/bookings/one-on-one",
    create_my_one_on_one_booking,
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
)
student_router.add_api_route(
    "/me/bookings/{booking_id}/cancel", cancel_my_booking, methods=["POST"]
)
student_router.add_api_route(
    "/me/bookings/{booking_id}/reschedule/one-on-one",
    reschedule_my_one_on_one_booking,
    methods=["POST"],
)
student_router.add_api_route(
    "/me/bookings/{booking_id}/reschedule/batch",
    reschedule_my_batch_booking,
    methods=["POST"],
)
student_router.add_api_route(
    "/me/batch-schedule-days", list_my_batch_schedule_days, methods=["GET"]
)
student_router.add_api_route(
    "/me/batch-schedule-days/{day_id}/selection",
    select_my_batch_day_option,
    methods=["PUT"],
)
student_router.add_api_route("/me/feedbacks", list_my_feedbacks, methods=["GET"])
