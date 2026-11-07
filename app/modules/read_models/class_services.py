from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_rows
from app.modules.batch_groups.models import BatchGroup
from app.modules.booking_notes.service import BookingNoteService
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.bookings.schemas import (
    AdminAddStudentToClass,
    BatchBookingReschedule,
    BookingActionRequest,
    ClassAttendanceMark,
    OneOnOneBookingCreate,
    OneOnOneBookingReschedule,
)
from app.modules.bookings.service import (
    BookingAttendanceService,
    BookingCancellationService,
    BookingCreationService,
    BookingQueryService,
    BookingRescheduleService,
)
from app.modules.classes.models import ClassSession
from app.modules.classes.schemas import BatchClassSessionCreate
from app.modules.classes.service import ClassSessionService
from app.modules.read_models.admin_schemas import (
    AdminActivityActorSummary,
    AdminActivityStudentSummary,
    AdminBatchClassReschedule,
    AdminBatchClassRescheduleResult,
    AdminClassActivityRead,
    AdminClassBatchGroupSummary,
    AdminClassBookingCounts,
    AdminClassRead,
    AdminClassRescheduleResult,
    AdminClassRosterBookingRead,
    AdminClassStudentSummary,
    AdminClassTeacherSummary,
    AdminStudentAccessState,
)
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.users.models import User
from app.shared.enums import (
    BookingStatus,
    ClassSessionStatus,
    SortOrder,
    StudentProgramType,
)


class _ServiceBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class AdminClassService(_ServiceBase):
    async def create_batch_class_session(
        self,
        class_session_in: BatchClassSessionCreate,
    ) -> ClassSession:
        return await ClassSessionService(self.session).create_batch_class_session(class_session_in)

    async def create_one_on_one_booking(
        self,
        booking_in: OneOnOneBookingCreate,
    ) -> Booking:
        return await BookingCreationService(self.session).create_one_on_one_booking(booking_in)

    async def list_class_sessions(
        self,
        pagination: PaginationParams,
        program_type: StudentProgramType | None = None,
        starts_from=None,
        starts_to=None,
        status: ClassSessionStatus | None = None,
        teacher_id: UUID | None = None,
        batch_group_id: UUID | None = None,
        sort_order: SortOrder = SortOrder.ASC,
        q: str | None = None,
    ) -> Page:
        normalized_q = _normalize_search_query(q)
        statement = self._admin_class_projection_statement(q=normalized_q)
        if program_type is not None:
            statement = statement.where(ClassSession.program_type == program_type)
        if starts_from is not None:
            statement = statement.where(ClassSession.starts_at >= starts_from)
        if starts_to is not None:
            statement = statement.where(ClassSession.starts_at <= starts_to)
        if status is not None:
            statement = statement.where(ClassSession.status == status)
        if teacher_id is not None:
            statement = statement.where(ClassSession.teacher_id == teacher_id)
        if batch_group_id is not None:
            statement = statement.where(ClassSession.batch_group_id == batch_group_id)

        starts_at_order = (
            ClassSession.starts_at.desc()
            if sort_order == SortOrder.DESC
            else ClassSession.starts_at.asc()
        )
        statement = statement.order_by(starts_at_order, ClassSession.id.asc())
        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[self._admin_class_from_row(row) for row in rows],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_class_session(self, class_session_id: UUID) -> AdminClassRead:
        row = (
            await self.session.execute(
                self._admin_class_projection_statement().where(ClassSession.id == class_session_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Class session not found")
        return self._admin_class_from_row(row)

    async def list_class_roster(
        self,
        class_session_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        await ClassSessionService(self.session).get_class_session(class_session_id)
        statement = (
            select(Booking, Student, User)
            .join(Student, Student.id == Booking.student_id)
            .join(User, User.id == Student.user_id)
            .where(Booking.class_session_id == class_session_id)
            .order_by(Booking.created_at.asc(), Booking.id.asc())
        )
        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[
                AdminClassRosterBookingRead.model_validate(
                    {
                        **_model_values(booking),
                        "student": AdminClassStudentSummary(
                            id=student.id,
                            user_id=student.user_id,
                            full_name=user.full_name,
                            email=user.email,
                            phone=user.phone,
                            status=student.status,
                        ),
                    }
                )
                for booking, student, user in rows
            ],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def list_class_activity(
        self,
        class_session_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        await ClassSessionService(self.session).get_class_session(class_session_id)
        student_user = aliased(User)
        actor_user = aliased(User)
        statement = (
            select(BookingEvent, Booking, Student, student_user, actor_user)
            .join(Booking, Booking.id == BookingEvent.booking_id)
            .join(Student, Student.id == Booking.student_id)
            .join(student_user, student_user.id == Student.user_id)
            .outerjoin(actor_user, actor_user.id == BookingEvent.actor_user_id)
            .where(Booking.class_session_id == class_session_id)
            .order_by(BookingEvent.created_at.desc(), BookingEvent.id.desc())
        )
        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[
                AdminClassActivityRead(
                    id=event.id,
                    class_session_id=class_session_id,
                    booking_id=booking.id,
                    student=AdminActivityStudentSummary(
                        id=student.id,
                        full_name=student_identity.full_name,
                        email=student_identity.email,
                    ),
                    event_type=event.event_type,
                    reason=event.reason,
                    metadata=event.event_metadata,
                    actor=(
                        AdminActivityActorSummary(
                            id=actor.id,
                            full_name=actor.full_name,
                            role=actor.role,
                        )
                        if actor is not None
                        else None
                    ),
                    actor_label=actor.full_name if actor is not None else "System",
                    created_at=event.created_at,
                )
                for event, booking, student, student_identity, actor in rows
            ],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    def _admin_class_projection_statement(self, *, q: str | None = None):
        teacher_user = aliased(User)
        primary_booking = aliased(Booking)
        primary_student = aliased(Student)
        primary_user = aliased(User)
        booking_counts = (
            select(
                Booking.class_session_id.label("class_session_id"),
                func.count().filter(Booking.status == BookingStatus.BOOKED).label("booked_count"),
                func.count()
                .filter(Booking.status == BookingStatus.CANCELLED)
                .label("cancelled_count"),
                func.count()
                .filter(Booking.status == BookingStatus.ATTENDED)
                .label("attended_count"),
                func.count().filter(Booking.status == BookingStatus.MISSED).label("missed_count"),
            )
            .group_by(Booking.class_session_id)
            .subquery()
        )
        statement = (
            select(
                ClassSession,
                Teacher.id.label("teacher_summary_id"),
                Teacher.display_name.label("teacher_display_name"),
                Teacher.profile_photo_url.label("teacher_profile_photo_url"),
                teacher_user.full_name.label("teacher_full_name"),
                BatchGroup.id.label("batch_summary_id"),
                BatchGroup.name.label("batch_name"),
                BatchGroup.is_active.label("batch_is_active"),
                primary_student.id.label("student_summary_id"),
                primary_student.user_id.label("student_user_id"),
                primary_student.status.label("student_status"),
                primary_user.full_name.label("student_full_name"),
                primary_user.email.label("student_email"),
                primary_user.phone.label("student_phone"),
                func.coalesce(booking_counts.c.booked_count, 0).label("booked_count"),
                func.coalesce(booking_counts.c.cancelled_count, 0).label("cancelled_count"),
                func.coalesce(booking_counts.c.attended_count, 0).label("attended_count"),
                func.coalesce(booking_counts.c.missed_count, 0).label("missed_count"),
            )
            .outerjoin(Teacher, Teacher.id == ClassSession.teacher_id)
            .outerjoin(teacher_user, teacher_user.id == Teacher.user_id)
            .outerjoin(BatchGroup, BatchGroup.id == ClassSession.batch_group_id)
            .outerjoin(
                primary_booking,
                (primary_booking.class_session_id == ClassSession.id)
                & (primary_booking.status != BookingStatus.CANCELLED)
                & (ClassSession.program_type == StudentProgramType.ONE_ON_ONE),
            )
            .outerjoin(primary_student, primary_student.id == primary_booking.student_id)
            .outerjoin(primary_user, primary_user.id == primary_student.user_id)
            .outerjoin(
                booking_counts,
                booking_counts.c.class_session_id == ClassSession.id,
            )
        )
        if q is not None:
            roster_user = aliased(User)
            roster_student = aliased(Student)
            roster_booking = aliased(Booking)
            roster_match = exists(
                select(roster_booking.id)
                .join(roster_student, roster_student.id == roster_booking.student_id)
                .join(roster_user, roster_user.id == roster_student.user_id)
                .where(
                    roster_booking.class_session_id == ClassSession.id,
                    roster_booking.status != BookingStatus.CANCELLED,
                    or_(
                        roster_user.full_name.ilike(f"%{q}%"),
                        roster_user.email.ilike(f"%{q}%"),
                        roster_user.phone.ilike(f"%{q}%"),
                    ),
                )
            )
            statement = statement.where(
                or_(
                    teacher_user.full_name.ilike(f"%{q}%"),
                    Teacher.display_name.ilike(f"%{q}%"),
                    BatchGroup.name.ilike(f"%{q}%"),
                    roster_match,
                )
            )
        return statement

    def _admin_class_from_row(self, row) -> AdminClassRead:
        values = row._mapping
        class_session = values[ClassSession]
        teacher = None
        if values["teacher_summary_id"] is not None:
            teacher = AdminClassTeacherSummary(
                id=values["teacher_summary_id"],
                display_name=values["teacher_display_name"],
                full_name=values["teacher_full_name"],
                profile_photo_url=values["teacher_profile_photo_url"],
            )
        batch_group = None
        if values["batch_summary_id"] is not None:
            batch_group = AdminClassBatchGroupSummary(
                id=values["batch_summary_id"],
                name=values["batch_name"],
                is_active=values["batch_is_active"],
            )
        primary_student = None
        if values["student_summary_id"] is not None:
            primary_student = AdminClassStudentSummary(
                id=values["student_summary_id"],
                user_id=values["student_user_id"],
                full_name=values["student_full_name"],
                email=values["student_email"],
                phone=values["student_phone"],
                status=values["student_status"],
            )
        return AdminClassRead.model_validate(
            {
                **_model_values(class_session),
                "teacher": teacher,
                "batch_group": batch_group,
                "primary_student": primary_student,
                "booking_counts": AdminClassBookingCounts(
                    booked=values["booked_count"],
                    cancelled=values["cancelled_count"],
                    attended=values["attended_count"],
                    missed=values["missed_count"],
                ),
            }
        )

    async def cancel_class_session(
        self,
        class_session_id: UUID,
        cancel_in: BookingActionRequest,
    ) -> AdminClassRead:
        await BookingCancellationService(self.session).admin_cancel_class_session(
            class_session_id,
            cancel_in,
        )
        return await self.get_class_session(class_session_id)

    async def add_student_to_class(
        self,
        class_session_id: UUID,
        add_in: AdminAddStudentToClass,
    ) -> Booking:
        return await BookingAttendanceService(self.session).admin_add_student_to_class(
            class_session_id,
            add_in,
        )

    async def mark_class_attendance(
        self,
        class_session_id: UUID,
        attendance_in: ClassAttendanceMark,
    ) -> list[Booking]:
        return await BookingAttendanceService(self.session).mark_class_attendance(
            class_session_id,
            attendance_in,
        )

    async def cancel_booking(
        self,
        booking_id: UUID,
        cancel_in: BookingActionRequest,
    ) -> Booking:
        return await BookingCancellationService(self.session).admin_cancel_booking(
            booking_id, cancel_in
        )

    async def list_bookings(
        self,
        pagination: PaginationParams,
        student_id: UUID | None = None,
        class_session_id: UUID | None = None,
        status: BookingStatus | None = None,
        teacher_id: UUID | None = None,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
    ) -> Page:
        return await BookingQueryService(self.session).list_bookings(
            pagination,
            student_id=student_id,
            class_session_id=class_session_id,
            status=status,
            teacher_id=teacher_id,
            starts_from=starts_from,
            starts_to=starts_to,
        )

    async def get_booking(self, booking_id: UUID) -> Booking:
        return await BookingQueryService(self.session).get_booking(booking_id)

    async def list_booking_events(
        self,
        booking_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        return await BookingQueryService(self.session).list_booking_events(booking_id, pagination)

    async def list_booking_notes(
        self,
        booking_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        return await BookingNoteService(self.session).list_admin_booking_notes(
            booking_id,
            pagination,
        )

    async def reschedule_one_on_one_booking(
        self,
        booking_id: UUID,
        reschedule_in: OneOnOneBookingReschedule,
    ) -> Booking:
        return await BookingRescheduleService(self.session).admin_reschedule_one_on_one_booking(
            booking_id,
            reschedule_in,
        )

    async def reschedule_batch_booking(
        self,
        booking_id: UUID,
        reschedule_in: BatchBookingReschedule,
    ) -> Booking:
        return await BookingRescheduleService(self.session).admin_reschedule_batch_booking(
            booking_id,
            reschedule_in,
        )

    async def reschedule_one_on_one_class(
        self,
        class_session_id: UUID,
        reschedule_in: OneOnOneBookingReschedule,
    ) -> AdminClassRescheduleResult:
        booking = await self.session.scalar(
            select(Booking).where(
                Booking.class_session_id == class_session_id,
                Booking.status == BookingStatus.BOOKED,
            )
        )
        if booking is None:
            class_session = await ClassSessionService(self.session).get_class_session(
                class_session_id
            )
            if class_session.program_type != StudentProgramType.ONE_ON_ONE:
                raise ConflictError("Class session is not one-on-one")
            raise ConflictError("One-on-one class does not have an active booking")
        new_booking = await BookingRescheduleService(
            self.session
        ).admin_reschedule_one_on_one_booking(
            booking.id,
            reschedule_in,
        )
        return AdminClassRescheduleResult(
            class_session=await self.get_class_session(new_booking.class_session_id),
            booking=new_booking,
        )

    async def reschedule_batch_class(
        self,
        class_session_id: UUID,
        reschedule_in: AdminBatchClassReschedule,
    ) -> AdminBatchClassRescheduleResult:
        bookings = await BookingRescheduleService(
            self.session
        ).admin_reschedule_batch_class_session(
            class_session_id,
            reschedule_in,
        )
        return AdminBatchClassRescheduleResult(
            class_session=await self.get_class_session(class_session_id),
            bookings=bookings,
        )


def _resolve_dashboard_window(
    *,
    starts_from: datetime | None,
    starts_to: datetime | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    if starts_from is None:
        starts_from = datetime.combine(now.date(), time.min, tzinfo=UTC)
    if starts_to is None:
        starts_to = starts_from + timedelta(days=1)
    if starts_from >= starts_to:
        raise ValueError("starts_from must be before starts_to")
    return starts_from, starts_to


def _normalize_search_query(q: str | None) -> str | None:
    if q is None:
        return None
    normalized = q.strip()
    return normalized or None


def _model_values(model) -> dict:
    return {key: value for key, value in vars(model).items() if not key.startswith("_")}


def _student_access_state_clause(access_state: AdminStudentAccessState, now: datetime):
    if access_state == AdminStudentAccessState.VALID:
        return (
            Student.access_starts_at.is_not(None)
            & (Student.access_starts_at <= now)
            & Student.access_ends_at.is_not(None)
            & (Student.access_ends_at > now)
        )
    if access_state == AdminStudentAccessState.EXPIRED:
        return Student.access_ends_at.is_not(None) & (Student.access_ends_at <= now)
    if access_state == AdminStudentAccessState.NOT_STARTED:
        return Student.access_starts_at.is_not(None) & (Student.access_starts_at > now)
    return or_(Student.access_starts_at.is_(None), Student.access_ends_at.is_(None))
