from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PaginationParams, paginate_rows
from app.modules.admin.schemas import (
    AdminDashboardBatchGroupSummary,
    AdminDashboardBookingSummary,
    AdminDashboardClassSummary,
    AdminDashboardPaymentSummary,
    AdminDashboardStudentSummary,
    AdminDashboardSummaryRead,
    AdminDashboardTeacherSummary,
    AdminDashboardWindowRead,
    AdminStudentAccessGrantCreate,
    AdminStudentAccessState,
    AdminStudentBatchGroupSet,
    AdminStudentCreate,
    AdminStudentPaymentCreate,
    AdminStudentRead,
    AdminTeacherCreate,
    AdminTeacherRead,
)
from app.modules.batch_groups.models import BatchGroup, StudentBatchMembership
from app.modules.batch_groups.schemas import BatchSessionBulkGenerate, StudentBatchTransfer
from app.modules.batch_groups.service import BatchGroupService
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    AdminAddStudentToClass,
    BatchBookingReschedule,
    BookingActionRequest,
    ClassAttendanceMark,
    OneOnOneBookingReschedule,
)
from app.modules.bookings.service import BookingService
from app.modules.classes.models import ClassSession
from app.modules.classes.schemas import BatchClassSessionCreate
from app.modules.classes.service import ClassSessionService
from app.modules.packages.models import Package
from app.modules.packages.service import PackageService
from app.modules.student_access_grants.models import StudentAccessGrant
from app.modules.student_access_grants.schemas import StudentAccessGrantCreate
from app.modules.student_access_grants.service import StudentAccessGrantService
from app.modules.student_payments.models import StudentPayment
from app.modules.student_payments.schemas import StudentPaymentCreate
from app.modules.student_payments.service import StudentPaymentService
from app.modules.students.models import Student, StudentProgramChange
from app.modules.students.schemas import StudentCreate, StudentProgramSwitch
from app.modules.students.service import StudentService
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherCreate
from app.modules.teachers.service import TeacherService
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService
from app.shared.enums import (
    BookingStatus,
    ClassSessionStatus,
    StudentProgramType,
    StudentStatus,
    UserRole,
)
from app.shared.utils import utc_now


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_teacher(self, teacher_in: AdminTeacherCreate) -> tuple[User, Teacher]:
        user = await UserService(self.session).create_user(
            UserCreate(
                full_name=teacher_in.full_name,
                email=teacher_in.email,
                phone=teacher_in.phone,
                role=UserRole.TEACHER,
                is_active=teacher_in.is_active,
            ),
            commit=False,
        )
        teacher = await TeacherService(self.session).create_teacher(
            TeacherCreate(
                user_id=user.id,
                display_name=teacher_in.display_name,
                bio=teacher_in.bio,
                profile_photo_url=teacher_in.profile_photo_url,
            ),
            commit=False,
        )

        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(teacher)
        return user, teacher

    async def create_student(self, student_in: AdminStudentCreate) -> tuple[User, Student]:
        user = await UserService(self.session).create_user(
            UserCreate(
                full_name=student_in.full_name,
                email=student_in.email,
                phone=student_in.phone,
                role=UserRole.STUDENT,
                is_active=student_in.is_active,
            ),
            commit=False,
        )
        student = await StudentService(self.session).create_student(
            StudentCreate(
                user_id=user.id,
                program_type=student_in.program_type,
                status=student_in.status,
                access_starts_at=student_in.access_starts_at,
                access_ends_at=student_in.access_ends_at,
                notes=student_in.notes,
            ),
            commit=False,
        )

        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(student)
        return user, student

    async def list_students(
        self,
        pagination: PaginationParams,
        q: str | None = None,
        status: StudentStatus | None = None,
        program_type: StudentProgramType | None = None,
        access_state: AdminStudentAccessState | None = None,
        batch_group_id: UUID | None = None,
    ) -> Page[AdminStudentRead]:
        statement = (
            select(Student, User)
            .join(User, Student.user_id == User.id)
            .order_by(Student.created_at.desc())
        )
        q = _normalize_search_query(q)
        if q is not None:
            pattern = f"%{q}%"
            statement = statement.where(
                or_(
                    User.full_name.ilike(pattern),
                    User.email.ilike(pattern),
                    User.phone.ilike(pattern),
                )
            )
        if status is not None:
            statement = statement.where(Student.status == status)
        if program_type is not None:
            statement = statement.where(Student.program_type == program_type)
        if access_state is not None:
            statement = statement.where(_student_access_state_clause(access_state, utc_now()))
        if batch_group_id is not None:
            statement = statement.where(
                exists()
                .where(StudentBatchMembership.student_id == Student.id)
                .where(StudentBatchMembership.batch_group_id == batch_group_id)
                .where(StudentBatchMembership.is_active.is_(True))
            )
        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[AdminStudentRead(student=student, user=user) for student, user in rows],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_student(self, student_id: UUID) -> AdminStudentRead:
        student = await StudentService(self.session).get_student(student_id)
        user = await UserService(self.session).get_user(student.user_id)
        return AdminStudentRead(student=student, user=user)

    async def list_teachers(
        self,
        pagination: PaginationParams,
        q: str | None = None,
        is_active: bool | None = None,
    ) -> Page[AdminTeacherRead]:
        statement = (
            select(Teacher, User)
            .join(User, Teacher.user_id == User.id)
            .order_by(Teacher.created_at.desc())
        )
        q = _normalize_search_query(q)
        if q is not None:
            pattern = f"%{q}%"
            statement = statement.where(
                or_(
                    Teacher.display_name.ilike(pattern),
                    User.full_name.ilike(pattern),
                    User.email.ilike(pattern),
                    User.phone.ilike(pattern),
                )
            )
        if is_active is not None:
            statement = statement.where(Teacher.is_active.is_(is_active))
        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[AdminTeacherRead(teacher=teacher, user=user) for teacher, user in rows],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_teacher(self, teacher_id: UUID) -> AdminTeacherRead:
        teacher = await TeacherService(self.session).get_teacher(teacher_id)
        user = await UserService(self.session).get_user(teacher.user_id)
        return AdminTeacherRead(teacher=teacher, user=user)

    async def get_dashboard_summary(
        self,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
        now: datetime | None = None,
    ) -> AdminDashboardSummaryRead:
        generated_at = now or utc_now()
        starts_from, starts_to = _resolve_dashboard_window(
            starts_from=starts_from,
            starts_to=starts_to,
            now=generated_at,
        )

        student_total = await self._count_rows(Student)
        student_status_counts = await self._count_grouped(Student.status)
        active_with_valid_access = await self._count_rows(
            Student,
            Student.status == StudentStatus.ACTIVE,
            Student.access_starts_at <= generated_at,
            Student.access_ends_at > generated_at,
        )
        expired_access = await self._count_rows(
            Student,
            Student.status == StudentStatus.ACTIVE,
            Student.access_ends_at <= generated_at,
        )

        teacher_total = await self._count_rows(Teacher)
        teacher_active_counts = await self._count_grouped(Teacher.is_active)

        batch_group_total = await self._count_rows(BatchGroup)
        batch_group_active_counts = await self._count_grouped(BatchGroup.is_active)

        class_status_counts = await self._count_grouped(
            ClassSession.status,
            ClassSession.starts_at >= starts_from,
            ClassSession.starts_at < starts_to,
        )
        booking_status_counts = await self._count_grouped(
            Booking.status,
            Booking.booked_at >= starts_from,
            Booking.booked_at < starts_to,
        )
        payment_count, total_amount_paid = await self._payment_summary(starts_from, starts_to)

        return AdminDashboardSummaryRead(
            window=AdminDashboardWindowRead(
                starts_from=starts_from,
                starts_to=starts_to,
                generated_at=generated_at,
            ),
            students=AdminDashboardStudentSummary(
                total=student_total,
                active=student_status_counts.get(StudentStatus.ACTIVE, 0),
                enrolled=student_status_counts.get(StudentStatus.ENROLLED, 0),
                paused=student_status_counts.get(StudentStatus.PAUSED, 0),
                completed=student_status_counts.get(StudentStatus.COMPLETED, 0),
                cancelled=student_status_counts.get(StudentStatus.CANCELLED, 0),
                active_with_valid_access=active_with_valid_access,
                expired_access=expired_access,
            ),
            teachers=AdminDashboardTeacherSummary(
                total=teacher_total,
                active=teacher_active_counts.get(True, 0),
                inactive=teacher_active_counts.get(False, 0),
            ),
            batch_groups=AdminDashboardBatchGroupSummary(
                total=batch_group_total,
                active=batch_group_active_counts.get(True, 0),
                inactive=batch_group_active_counts.get(False, 0),
            ),
            classes=AdminDashboardClassSummary(
                scheduled=class_status_counts.get(ClassSessionStatus.SCHEDULED, 0),
                completed=class_status_counts.get(ClassSessionStatus.COMPLETED, 0),
                cancelled=class_status_counts.get(ClassSessionStatus.CANCELLED, 0),
            ),
            bookings=AdminDashboardBookingSummary(
                booked=booking_status_counts.get(BookingStatus.BOOKED, 0),
                cancelled=booking_status_counts.get(BookingStatus.CANCELLED, 0),
                attended=booking_status_counts.get(BookingStatus.ATTENDED, 0),
                missed=booking_status_counts.get(BookingStatus.MISSED, 0),
            ),
            payments=AdminDashboardPaymentSummary(
                count=payment_count,
                total_amount_paid=total_amount_paid,
            ),
        )

    async def _count_rows(self, model, *where_clauses) -> int:
        statement = select(func.count()).select_from(model)
        if where_clauses:
            statement = statement.where(*where_clauses)
        return await self.session.scalar(statement) or 0

    async def _count_grouped(self, column, *where_clauses) -> dict:
        statement = select(column, func.count()).group_by(column)
        if where_clauses:
            statement = statement.where(*where_clauses)
        result = await self.session.execute(statement)
        return {key: count for key, count in result.all()}

    async def _payment_summary(self, starts_from: datetime, starts_to: datetime) -> tuple[int, int]:
        statement = select(
            func.count(StudentPayment.id),
            func.coalesce(func.sum(StudentPayment.amount_paid), 0),
        ).where(
            StudentPayment.paid_at >= starts_from,
            StudentPayment.paid_at < starts_to,
        )
        result = await self.session.execute(statement)
        payment_count, total_amount_paid = result.one()
        return int(payment_count), int(total_amount_paid)

    async def list_student_payments(
        self,
        student_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        return await StudentPaymentService(self.session).list_payments(
            pagination,
            student_id=student_id,
        )

    async def create_student_payment(
        self,
        student_id: UUID,
        payment_in: AdminStudentPaymentCreate,
    ) -> StudentPayment:
        return await StudentPaymentService(self.session).create_payment(
            StudentPaymentCreate(
                student_id=student_id,
                package_id=payment_in.package_id,
                amount_paid=payment_in.amount_paid,
                currency=payment_in.currency,
                payment_method=payment_in.payment_method,
                paid_at=payment_in.paid_at,
                created_by_user_id=payment_in.created_by_user_id,
                notes=payment_in.notes,
            )
        )

    async def list_student_access_grants(
        self,
        student_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        return await StudentAccessGrantService(self.session).list_grants(
            pagination,
            student_id=student_id,
        )

    async def create_student_access_grant(
        self,
        student_id: UUID,
        grant_in: AdminStudentAccessGrantCreate,
    ) -> StudentAccessGrant:
        return await StudentAccessGrantService(self.session).create_grant(
            StudentAccessGrantCreate(
                student_id=student_id,
                package_id=grant_in.package_id,
                grant_type=grant_in.grant_type,
                duration_days=grant_in.duration_days,
                access_starts_at=grant_in.access_starts_at,
                extend_current_access=grant_in.extend_current_access,
                created_by_user_id=grant_in.created_by_user_id,
                notes=grant_in.notes,
            )
        )

    async def switch_student_program(
        self,
        student_id: UUID,
        switch_in: StudentProgramSwitch,
    ) -> StudentProgramChange:
        return await StudentService(self.session).switch_program(student_id, switch_in)

    async def set_student_batch_group(
        self,
        student_id: UUID,
        batch_group_in: AdminStudentBatchGroupSet,
    ) -> StudentBatchMembership:
        return await BatchGroupService(self.session).transfer_student_batch_group(
            student_id,
            StudentBatchTransfer(
                batch_group_id=batch_group_in.batch_group_id,
                assigned_by_user_id=batch_group_in.assigned_by_user_id,
                reason=batch_group_in.reason,
            ),
        )

    async def list_student_batch_memberships(
        self,
        student_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        return await BatchGroupService(self.session).list_student_batch_memberships(
            student_id,
            pagination,
        )

    async def list_batch_groups(
        self,
        pagination: PaginationParams,
        is_active: bool | None = None,
    ) -> Page:
        return await BatchGroupService(self.session).list_batch_groups(
            pagination,
            is_active=is_active,
        )

    async def get_batch_group(self, batch_group_id: UUID) -> BatchGroup:
        return await BatchGroupService(self.session).get_batch_group(batch_group_id)

    async def list_batch_group_students(
        self,
        batch_group_id: UUID,
        pagination: PaginationParams,
        is_active: bool | None = True,
    ) -> Page:
        return await BatchGroupService(self.session).list_batch_group_students(
            batch_group_id=batch_group_id,
            pagination=pagination,
            is_active=is_active,
        )

    async def list_packages(self, pagination: PaginationParams) -> Page:
        return await PackageService(self.session).list_packages(pagination)

    async def get_package(self, package_id: UUID) -> Package:
        return await PackageService(self.session).get_package(package_id)

    async def generate_batch_sessions(
        self,
        batch_group_id: UUID,
        generation_in: BatchSessionBulkGenerate,
    ) -> list[ClassSession]:
        return await BatchGroupService(self.session).generate_batch_sessions(
            batch_group_id,
            generation_in,
        )

    async def create_batch_class_session(
        self,
        class_session_in: BatchClassSessionCreate,
    ) -> ClassSession:
        return await ClassSessionService(self.session).create_batch_class_session(class_session_in)

    async def list_class_sessions(
        self,
        pagination: PaginationParams,
        program_type: StudentProgramType | None = None,
        starts_from=None,
        starts_to=None,
    ) -> Page:
        return await ClassSessionService(self.session).list_class_sessions(
            pagination,
            program_type=program_type,
            starts_from=starts_from,
            starts_to=starts_to,
        )

    async def get_class_session(self, class_session_id: UUID) -> ClassSession:
        return await ClassSessionService(self.session).get_class_session(class_session_id)

    async def add_student_to_class(
        self,
        class_session_id: UUID,
        add_in: AdminAddStudentToClass,
    ) -> Booking:
        return await BookingService(self.session).admin_add_student_to_class(
            class_session_id,
            add_in,
        )

    async def mark_class_attendance(
        self,
        class_session_id: UUID,
        attendance_in: ClassAttendanceMark,
    ) -> list[Booking]:
        return await BookingService(self.session).mark_class_attendance(
            class_session_id,
            attendance_in,
        )

    async def cancel_booking(
        self,
        booking_id: UUID,
        cancel_in: BookingActionRequest,
    ) -> Booking:
        return await BookingService(self.session).admin_cancel_booking(booking_id, cancel_in)

    async def list_bookings(
        self,
        pagination: PaginationParams,
        student_id: UUID | None = None,
        class_session_id: UUID | None = None,
    ) -> Page:
        return await BookingService(self.session).list_bookings(
            pagination,
            student_id=student_id,
            class_session_id=class_session_id,
        )

    async def get_booking(self, booking_id: UUID) -> Booking:
        return await BookingService(self.session).get_booking(booking_id)

    async def list_booking_events(
        self,
        booking_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        return await BookingService(self.session).list_booking_events(booking_id, pagination)

    async def reschedule_one_on_one_booking(
        self,
        booking_id: UUID,
        reschedule_in: OneOnOneBookingReschedule,
    ) -> Booking:
        return await BookingService(self.session).admin_reschedule_one_on_one_booking(
            booking_id,
            reschedule_in,
        )

    async def reschedule_batch_booking(
        self,
        booking_id: UUID,
        reschedule_in: BatchBookingReschedule,
    ) -> Booking:
        return await BookingService(self.session).admin_reschedule_batch_booking(
            booking_id,
            reschedule_in,
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
