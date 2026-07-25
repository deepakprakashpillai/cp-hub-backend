from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_rows
from app.modules.admin.schemas import (
    AdminActivityActorSummary,
    AdminActivityStudentSummary,
    AdminBatchClassReschedule,
    AdminBatchClassRescheduleResult,
    AdminBatchGroupRead,
    AdminBatchGroupSortBy,
    AdminClassActivityRead,
    AdminClassBatchGroupSummary,
    AdminClassBookingCounts,
    AdminClassRead,
    AdminClassRescheduleResult,
    AdminClassRosterBookingRead,
    AdminClassStudentSummary,
    AdminClassTeacherSummary,
    AdminDashboardBatchGroupSummary,
    AdminDashboardBookingSummary,
    AdminDashboardClassSummary,
    AdminDashboardPaymentSummary,
    AdminDashboardStudentSummary,
    AdminDashboardSummaryRead,
    AdminDashboardTeacherSummary,
    AdminDashboardWindowRead,
    AdminPackageSortBy,
    AdminStudentAccessGrantCreate,
    AdminStudentAccessState,
    AdminStudentBatchGroupSet,
    AdminStudentCreate,
    AdminStudentPaymentCreate,
    AdminStudentPaymentUpdate,
    AdminStudentRead,
    AdminStudentSortBy,
    AdminStudentUpdate,
    AdminTeacherCreate,
    AdminTeacherRead,
    AdminTeacherSortBy,
    SortOrder,
)
from app.modules.batch_groups.models import BatchGroup, StudentBatchMembership
from app.modules.batch_groups.schemas import (
    BatchGroupCreate,
    BatchGroupUpdate,
    BatchSessionBulkGenerate,
    StudentBatchMembershipAssign,
    StudentBatchTransfer,
)
from app.modules.batch_groups.service import BatchGroupService
from app.modules.batch_schedule_days.schemas import (
    BatchDayActionRequest,
    BatchDayAllocationRequest,
    BatchDayAllocationResult,
    BatchDayBulkCancelRequest,
    BatchDayBulkCancelResult,
    BatchDayBulkCreate,
    BatchDayBulkCreateResult,
    BatchDayCreate,
    BatchDayOptionCreate,
    BatchDayOptionUpdate,
    BatchScheduleDayRead,
    BatchScheduleDefaultsUpdate,
)
from app.modules.batch_schedule_days.service import BatchScheduleDayService
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
from app.modules.bookings.service import BookingService
from app.modules.classes.models import ClassSession
from app.modules.classes.schemas import BatchClassSessionCreate
from app.modules.classes.service import ClassSessionService
from app.modules.packages.models import Package
from app.modules.packages.schemas import PackageCreate, PackageUpdate
from app.modules.packages.service import PackageService
from app.modules.schedules.models import TeacherAvailabilityRule, TeacherAvailabilitySlot
from app.modules.schedules.schemas import (
    TeacherAvailabilityBlockCreate,
    TeacherAvailabilityRuleCreate,
    TeacherAvailabilityRuleUpdate,
    TeacherAvailabilitySlotBulkCreate,
    TeacherAvailabilitySlotCreate,
    TeacherAvailabilitySlotUpdate,
)
from app.modules.schedules.service import ScheduleService
from app.modules.student_access_grants.models import StudentAccessGrant
from app.modules.student_access_grants.schemas import StudentAccessGrantCreate
from app.modules.student_access_grants.service import StudentAccessGrantService
from app.modules.student_payments.models import StudentPayment
from app.modules.student_payments.schemas import StudentPaymentCreate, StudentPaymentUpdate
from app.modules.student_payments.service import StudentPaymentService
from app.modules.students.models import Student, StudentProgramChange
from app.modules.students.schemas import StudentCreate, StudentProgramSwitch, StudentUpdate
from app.modules.students.service import StudentService
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherCreate, TeacherUpdate
from app.modules.teachers.service import TeacherService
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserUpdate
from app.modules.users.service import UserService
from app.shared.enums import (
    AvailabilitySlotSource,
    AvailabilitySlotStatus,
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
        assigned_teacher_id: UUID | None = None,
        sort_by: AdminStudentSortBy = AdminStudentSortBy.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> Page[AdminStudentRead]:
        sort_columns = {
            AdminStudentSortBy.CREATED_AT: Student.created_at,
            AdminStudentSortBy.JOINED_AT: Student.joined_at,
            AdminStudentSortBy.NAME: User.full_name,
            AdminStudentSortBy.STATUS: Student.status,
            AdminStudentSortBy.PROGRAM_TYPE: Student.program_type,
            AdminStudentSortBy.ACCESS_ENDS_AT: Student.access_ends_at,
        }
        sort_column = sort_columns[sort_by]
        sort_expression = (
            sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
        )
        assigned_teacher_user = aliased(User)
        statement = (
            select(Student, User, Teacher, assigned_teacher_user)
            .join(User, Student.user_id == User.id)
            .outerjoin(Teacher, Student.assigned_teacher_id == Teacher.id)
            .outerjoin(assigned_teacher_user, Teacher.user_id == assigned_teacher_user.id)
            .order_by(sort_expression.nulls_last(), Student.id.asc())
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
        if assigned_teacher_id is not None:
            statement = statement.where(
                Student.assigned_teacher_id == assigned_teacher_id
            )
        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[
                AdminStudentRead(
                    student=student,
                    user=user,
                    assigned_teacher=(
                        AdminTeacherRead(teacher=teacher, user=teacher_user)
                        if teacher is not None and teacher_user is not None
                        else None
                    ),
                )
                for student, user, teacher, teacher_user in rows
            ],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_student(self, student_id: UUID) -> AdminStudentRead:
        student = await StudentService(self.session).get_student(student_id)
        user = await UserService(self.session).get_user(student.user_id)
        assigned_teacher = None
        if student.assigned_teacher_id is not None:
            teacher = await TeacherService(self.session).get_teacher(
                student.assigned_teacher_id
            )
            teacher_user = await UserService(self.session).get_user(teacher.user_id)
            assigned_teacher = AdminTeacherRead(teacher=teacher, user=teacher_user)
        return AdminStudentRead(
            student=student,
            user=user,
            assigned_teacher=assigned_teacher,
        )

    async def update_student(
        self,
        student_id: UUID,
        student_in: AdminStudentUpdate,
    ) -> AdminStudentRead:
        update_data = student_in.model_dump(exclude_unset=True)
        program_type = update_data.pop("program_type", None)
        assigned_teacher_id = update_data.pop("assigned_teacher_id", None)
        assigned_teacher_was_set = "assigned_teacher_id" in student_in.model_fields_set
        if "program_type" in student_in.model_fields_set and program_type is None:
            raise BadRequestError("program_type cannot be null")

        student_service = StudentService(self.session)
        current_student = await student_service.get_student(student_id)
        final_program_type = program_type or current_student.program_type
        if assigned_teacher_was_set and assigned_teacher_id is not None:
            if final_program_type != StudentProgramType.ONE_ON_ONE:
                raise BadRequestError(
                    "Assigned teacher is only valid for one-on-one students"
                )
            teacher = await TeacherService(self.session).get_teacher(assigned_teacher_id)
            if not teacher.is_active:
                raise BadRequestError("Assigned teacher must be active")

        if update_data:
            student = await student_service.update_student(student_id, StudentUpdate(**update_data))
        else:
            student = current_student

        if program_type is not None and program_type != student.program_type:
            await student_service.switch_program(
                student_id,
                StudentProgramSwitch(new_program_type=program_type),
            )
        if assigned_teacher_was_set:
            await student_service.set_assigned_teacher(student_id, assigned_teacher_id)

        return await self.get_student(student_id)

    async def list_teachers(
        self,
        pagination: PaginationParams,
        q: str | None = None,
        is_active: bool | None = None,
        account_is_active: bool | None = None,
        sort_by: AdminTeacherSortBy = AdminTeacherSortBy.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> Page[AdminTeacherRead]:
        sort_columns = {
            AdminTeacherSortBy.CREATED_AT: Teacher.created_at,
            AdminTeacherSortBy.NAME: User.full_name,
            AdminTeacherSortBy.DISPLAY_NAME: Teacher.display_name,
            AdminTeacherSortBy.IS_ACTIVE: Teacher.is_active,
        }
        sort_column = sort_columns[sort_by]
        sort_expression = (
            sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
        )
        statement = (
            select(Teacher, User)
            .join(User, Teacher.user_id == User.id)
            .order_by(sort_expression.nulls_last(), Teacher.id.asc())
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
        if account_is_active is not None:
            statement = statement.where(User.is_active.is_(account_is_active))
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

    async def update_teacher(
        self,
        teacher_id: UUID,
        teacher_in: TeacherUpdate,
    ) -> AdminTeacherRead:
        teacher = await TeacherService(self.session).update_teacher(teacher_id, teacher_in)
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

    async def update_student_payment(
        self,
        student_id: UUID,
        payment_id: UUID,
        payment_in: AdminStudentPaymentUpdate,
    ) -> StudentPayment:
        payment_service = StudentPaymentService(self.session)
        payment = await payment_service.get_payment(payment_id)
        if payment.student_id != student_id:
            raise ConflictError("Payment does not belong to student")
        return await payment_service.update_payment(
            payment_id,
            StudentPaymentUpdate(**payment_in.model_dump(exclude_unset=True)),
        )

    async def delete_student_payment(self, student_id: UUID, payment_id: UUID) -> None:
        payment_service = StudentPaymentService(self.session)
        payment = await payment_service.get_payment(payment_id)
        if payment.student_id != student_id:
            raise ConflictError("Payment does not belong to student")
        await payment_service.delete_payment(payment_id)

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
                allow_package_access_override=(
                    batch_group_in.allow_package_access_override
                ),
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
        q: str | None = None,
        sort_by: AdminBatchGroupSortBy = AdminBatchGroupSortBy.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> Page:
        now = utc_now()
        active_members = (
            select(
                StudentBatchMembership.batch_group_id.label("batch_group_id"),
                func.count().label("active_member_count"),
            )
            .where(StudentBatchMembership.is_active.is_(True))
            .group_by(StudentBatchMembership.batch_group_id)
            .subquery()
        )

        upcoming_sessions = (
            select(
                ClassSession.batch_group_id.label("batch_group_id"),
                func.count().label("upcoming_scheduled_count"),
            )
            .where(
                ClassSession.status == ClassSessionStatus.SCHEDULED,
                ClassSession.starts_at > now,
            )
            .group_by(ClassSession.batch_group_id)
            .subquery()
        )
        active_member_count = func.coalesce(active_members.c.active_member_count, 0)
        upcoming_scheduled_count = func.coalesce(
            upcoming_sessions.c.upcoming_scheduled_count,
            0,
        )
        sort_columns = {
            AdminBatchGroupSortBy.CREATED_AT: BatchGroup.created_at,
            AdminBatchGroupSortBy.NAME: BatchGroup.name,
            AdminBatchGroupSortBy.ACTIVE_MEMBER_COUNT: active_member_count,
            AdminBatchGroupSortBy.UPCOMING_SCHEDULED_COUNT: upcoming_scheduled_count,
            AdminBatchGroupSortBy.IS_ACTIVE: BatchGroup.is_active,
        }
        sort_column = sort_columns[sort_by]
        order_expression = (
            sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
        )
        statement = (
            select(
                BatchGroup,
                active_member_count.label("active_member_count"),
                upcoming_scheduled_count.label("upcoming_scheduled_count"),
            )
            .outerjoin(
                active_members,
                active_members.c.batch_group_id == BatchGroup.id,
            )
            .outerjoin(
                upcoming_sessions,
                upcoming_sessions.c.batch_group_id == BatchGroup.id,
            )
            .order_by(order_expression, BatchGroup.id.asc())
        )
        if is_active is not None:
            statement = statement.where(BatchGroup.is_active.is_(is_active))
        normalized_q = _normalize_search_query(q)
        if normalized_q is not None:
            statement = statement.where(BatchGroup.name.ilike(f"%{normalized_q}%"))

        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[
                AdminBatchGroupRead.model_validate(
                    {
                        **_model_values(batch_group),
                        "package": batch_group.package,
                        "active_member_count": active_count,
                        "upcoming_scheduled_count": upcoming_count,
                    }
                )
                for batch_group, active_count, upcoming_count in rows
            ],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_batch_schedule_defaults(self):
        return await BatchScheduleDayService(self.session).get_defaults()

    async def update_batch_schedule_defaults(self, defaults_in: BatchScheduleDefaultsUpdate):
        return await BatchScheduleDayService(self.session).update_defaults(defaults_in)

    async def create_batch_schedule_day(
        self,
        day_in: BatchDayCreate,
    ) -> BatchScheduleDayRead:
        return await BatchScheduleDayService(self.session).create_day(day_in)

    async def create_batch_schedule_days_bulk(
        self,
        bulk_in: BatchDayBulkCreate,
    ) -> BatchDayBulkCreateResult:
        return await BatchScheduleDayService(self.session).create_days_bulk(bulk_in)

    async def list_batch_schedule_days(
        self,
        pagination: PaginationParams,
        *,
        batch_group_id: UUID | None = None,
        starts_from=None,
        starts_to=None,
    ) -> Page:
        return await BatchScheduleDayService(self.session).list_days(
            pagination,
            batch_group_id=batch_group_id,
            starts_from=starts_from,
            starts_to=starts_to,
        )

    async def get_batch_schedule_day(self, day_id: UUID) -> BatchScheduleDayRead:
        return await BatchScheduleDayService(self.session).get_day(day_id)

    async def cancel_batch_schedule_day(
        self,
        day_id: UUID,
        action_in: BatchDayActionRequest,
    ) -> BatchScheduleDayRead:
        return await BatchScheduleDayService(self.session).cancel_day(day_id, action_in)

    async def cancel_batch_schedule_days_bulk(
        self,
        cancel_in: BatchDayBulkCancelRequest,
    ) -> BatchDayBulkCancelResult:
        return await BatchScheduleDayService(self.session).cancel_days_bulk(cancel_in)

    async def add_batch_schedule_day_option(
        self,
        day_id: UUID,
        option_in: BatchDayOptionCreate,
    ) -> BatchScheduleDayRead:
        return await BatchScheduleDayService(self.session).add_option(day_id, option_in)

    async def update_batch_schedule_day_option(
        self,
        day_id: UUID,
        class_session_id: UUID,
        option_in: BatchDayOptionUpdate,
    ) -> BatchScheduleDayRead:
        return await BatchScheduleDayService(self.session).update_option(
            day_id,
            class_session_id,
            option_in,
        )

    async def remove_batch_schedule_day_option(
        self,
        day_id: UUID,
        class_session_id: UUID,
    ) -> BatchScheduleDayRead:
        return await BatchScheduleDayService(self.session).remove_option(
            day_id,
            class_session_id,
        )

    async def assign_batch_day_student(
        self,
        day_id: UUID,
        student_id: UUID,
        allocation_in: BatchDayAllocationRequest,
    ) -> BatchDayAllocationResult:
        booking, moved_from = await BookingService(self.session).select_batch_day_option(
            student_id=student_id,
            batch_schedule_day_id=day_id,
            class_session_id=allocation_in.class_session_id,
            admin_override=True,
            actor_user_id=allocation_in.actor_user_id,
            reason=allocation_in.reason,
        )
        return BatchDayAllocationResult(
            booking=booking,
            moved_from_booking_id=moved_from,
        )

    async def remove_batch_day_student(
        self,
        day_id: UUID,
        student_id: UUID,
        action_in: BatchDayActionRequest,
    ) -> Booking:
        return await BookingService(self.session).remove_batch_day_selection(
            student_id=student_id,
            batch_schedule_day_id=day_id,
            actor_user_id=action_in.actor_user_id,
            reason=action_in.reason,
        )

    async def create_batch_group(self, batch_group_in: BatchGroupCreate) -> BatchGroup:
        return await BatchGroupService(self.session).create_batch_group(batch_group_in)

    async def get_batch_group(self, batch_group_id: UUID) -> AdminBatchGroupRead:
        now = utc_now()
        row = (
            await self.session.execute(
                select(
                    BatchGroup,
                    select(func.count())
                    .select_from(StudentBatchMembership)
                    .where(
                        StudentBatchMembership.batch_group_id == BatchGroup.id,
                        StudentBatchMembership.is_active.is_(True),
                    )
                    .correlate(BatchGroup)
                    .scalar_subquery()
                    .label("active_member_count"),
                    select(func.count())
                    .select_from(ClassSession)
                    .where(
                        ClassSession.batch_group_id == BatchGroup.id,
                        ClassSession.status == ClassSessionStatus.SCHEDULED,
                        ClassSession.starts_at > now,
                    )
                    .correlate(BatchGroup)
                    .scalar_subquery()
                    .label("upcoming_scheduled_count"),
                ).where(BatchGroup.id == batch_group_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Batch group not found")
        batch_group, active_count, upcoming_count = row
        return AdminBatchGroupRead.model_validate(
            {
                **_model_values(batch_group),
                "package": batch_group.package,
                "active_member_count": active_count,
                "upcoming_scheduled_count": upcoming_count,
            }
        )

    async def update_batch_group(
        self,
        batch_group_id: UUID,
        batch_group_in: BatchGroupUpdate,
    ) -> BatchGroup:
        return await BatchGroupService(self.session).update_batch_group(
            batch_group_id,
            batch_group_in,
        )

    async def void_batch_group(self, batch_group_id: UUID) -> BatchGroup:
        return await BatchGroupService(self.session).void_batch_group(batch_group_id)

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

    async def add_student_to_batch_group(
        self,
        batch_group_id: UUID,
        membership_in: StudentBatchMembershipAssign,
    ) -> StudentBatchMembership:
        return await BatchGroupService(self.session).assign_student_to_batch_group(
            batch_group_id,
            membership_in,
        )

    async def remove_student_from_batch_group(
        self,
        batch_group_id: UUID,
        student_id: UUID,
        *,
        reason: str | None,
    ) -> StudentBatchMembership:
        return await BatchGroupService(self.session).remove_student_from_batch_group(
            batch_group_id,
            student_id,
            reason=reason,
        )

    async def list_packages(
        self,
        pagination: PaginationParams,
        *,
        q: str | None = None,
        is_active: bool | None = None,
        sort_by: AdminPackageSortBy = AdminPackageSortBy.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> Page:
        sort_columns = {
            AdminPackageSortBy.CREATED_AT: Package.created_at,
            AdminPackageSortBy.NAME: Package.name,
            AdminPackageSortBy.DURATION_DAYS: Package.duration_days,
            AdminPackageSortBy.PRICE_AMOUNT: Package.price_amount,
            AdminPackageSortBy.IS_ACTIVE: Package.is_active,
        }
        sort_column = sort_columns[sort_by]
        order_expression = (
            sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
        )
        statement = select(Package).order_by(order_expression, Package.id.asc())
        normalized_q = _normalize_search_query(q)
        if normalized_q is not None:
            statement = statement.where(Package.name.ilike(f"%{normalized_q}%"))
        if is_active is not None:
            statement = statement.where(Package.is_active.is_(is_active))
        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[row[0] for row in rows],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def create_package(self, package_in: PackageCreate) -> Package:
        return await PackageService(self.session).create_package(package_in)

    async def get_package(self, package_id: UUID) -> Package:
        return await PackageService(self.session).get_package(package_id)

    async def update_package(self, package_id: UUID, package_in: PackageUpdate) -> Package:
        return await PackageService(self.session).update_package(package_id, package_in)

    async def void_package(self, package_id: UUID) -> Package:
        return await PackageService(self.session).void_package(package_id)

    async def update_user(self, user_id: UUID, user_in: UserUpdate) -> User:
        return await UserService(self.session).update_user(user_id, user_in)

    async def list_teacher_availability_rules(
        self,
        pagination: PaginationParams,
        teacher_id: UUID | None = None,
    ) -> Page:
        return await ScheduleService(self.session).list_teacher_availability_rules(
            pagination,
            teacher_id=teacher_id,
        )

    async def create_teacher_availability_rule(
        self,
        rule_in: TeacherAvailabilityRuleCreate,
    ) -> TeacherAvailabilityRule:
        return await ScheduleService(self.session).create_teacher_availability_rule(rule_in)

    async def get_teacher_availability_rule(self, rule_id: UUID) -> TeacherAvailabilityRule:
        return await ScheduleService(self.session).get_teacher_availability_rule(rule_id)

    async def update_teacher_availability_rule(
        self,
        rule_id: UUID,
        rule_in: TeacherAvailabilityRuleUpdate,
    ) -> TeacherAvailabilityRule:
        return await ScheduleService(self.session).update_teacher_availability_rule(
            rule_id,
            rule_in,
        )

    async def delete_teacher_availability_rule(self, rule_id: UUID) -> None:
        await ScheduleService(self.session).delete_teacher_availability_rule(rule_id)

    async def list_teacher_availability_slots(
        self,
        pagination: PaginationParams,
        teacher_id: UUID | None = None,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
        status: AvailabilitySlotStatus | None = None,
        source: AvailabilitySlotSource | None = None,
        sort_order: SortOrder = SortOrder.ASC,
    ) -> Page:
        return await ScheduleService(self.session).list_teacher_availability_slots(
            pagination,
            teacher_id=teacher_id,
            starts_from=starts_from,
            starts_to=starts_to,
            status=status,
            source=source,
            descending=sort_order == SortOrder.DESC,
        )

    async def create_teacher_availability_slot(
        self,
        slot_in: TeacherAvailabilitySlotCreate,
    ) -> TeacherAvailabilitySlot:
        return await ScheduleService(self.session).create_teacher_availability_slot(slot_in)

    async def create_teacher_availability_slots_bulk(
        self,
        slots_in: TeacherAvailabilitySlotBulkCreate,
    ) -> list[TeacherAvailabilitySlot]:
        return await ScheduleService(self.session).create_teacher_availability_slots_bulk(slots_in)

    async def create_teacher_availability_block(
        self,
        block_in: TeacherAvailabilityBlockCreate,
    ) -> TeacherAvailabilitySlot:
        return await ScheduleService(self.session).create_teacher_availability_block(block_in)

    async def get_teacher_availability_slot(self, slot_id: UUID) -> TeacherAvailabilitySlot:
        return await ScheduleService(self.session).get_teacher_availability_slot(slot_id)

    async def update_teacher_availability_slot(
        self,
        slot_id: UUID,
        slot_in: TeacherAvailabilitySlotUpdate,
    ) -> TeacherAvailabilitySlot:
        return await ScheduleService(self.session).update_teacher_availability_slot(
            slot_id,
            slot_in,
        )

    async def delete_teacher_availability_slot(self, slot_id: UUID) -> None:
        await ScheduleService(self.session).delete_teacher_availability_slot(slot_id)

    async def generate_teacher_availability_slots(
        self,
        teacher_id: UUID,
        days_ahead: int = 14,
    ):
        return await ScheduleService(self.session).generate_teacher_availability_slots(
            teacher_id,
            days_ahead=days_ahead,
        )

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

    async def create_one_on_one_booking(
        self,
        booking_in: OneOnOneBookingCreate,
    ) -> Booking:
        return await BookingService(self.session).create_one_on_one_booking(booking_in)

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
                self._admin_class_projection_statement().where(
                    ClassSession.id == class_session_id
                )
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
        await BookingService(self.session).admin_cancel_class_session(
            class_session_id,
            cancel_in,
        )
        return await self.get_class_session(class_session_id)

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
        status: BookingStatus | None = None,
        teacher_id: UUID | None = None,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
    ) -> Page:
        return await BookingService(self.session).list_bookings(
            pagination,
            student_id=student_id,
            class_session_id=class_session_id,
            status=status,
            teacher_id=teacher_id,
            starts_from=starts_from,
            starts_to=starts_to,
        )

    async def get_booking(self, booking_id: UUID) -> Booking:
        return await BookingService(self.session).get_booking(booking_id)

    async def list_booking_events(
        self,
        booking_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        return await BookingService(self.session).list_booking_events(booking_id, pagination)

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
        new_booking = await BookingService(self.session).admin_reschedule_one_on_one_booking(
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
        bookings = await BookingService(self.session).admin_reschedule_batch_class_session(
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
