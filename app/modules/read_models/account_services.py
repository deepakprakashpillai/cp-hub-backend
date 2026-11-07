from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import BadRequestError
from app.core.pagination import Page, PaginationParams, paginate_rows
from app.modules.auth.email import send_password_setup_email
from app.modules.auth.service import AuthService
from app.modules.batch_groups.models import StudentBatchMembership
from app.modules.read_models.admin_schemas import (
    AdminStudentAccessState,
    AdminStudentCreate,
    AdminStudentRead,
    AdminStudentSortBy,
    AdminStudentUpdate,
    AdminTeacherCreate,
    AdminTeacherRead,
    AdminTeacherSortBy,
)
from app.modules.students.models import Student
from app.modules.students.schemas import StudentCreate, StudentProgramSwitch, StudentUpdate
from app.modules.students.service import StudentService
from app.modules.students.workflows import StudentProgramWorkflow
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherCreate, TeacherUpdate
from app.modules.teachers.service import TeacherService
from app.modules.teachers.workflows import TeacherLifecycleWorkflow
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService
from app.shared.enums import (
    SortOrder,
    StudentProgramType,
    StudentStatus,
    UserRole,
)
from app.shared.utils import utc_now


class _ServiceBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class AdminAccountWorkflow(_ServiceBase):
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
        setup_token = await AuthService(self.session).issue_password_token(user, "setup")
        await self.session.commit()
        await send_password_setup_email(user.email, setup_token)
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
        sort_expression = sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
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
            statement = statement.where(Student.assigned_teacher_id == assigned_teacher_id)
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
            teacher = await TeacherService(self.session).get_teacher(student.assigned_teacher_id)
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
                raise BadRequestError("Assigned teacher is only valid for one-on-one students")
            teacher = await TeacherService(self.session).get_teacher(assigned_teacher_id)
            if not teacher.is_active:
                raise BadRequestError("Assigned teacher must be active")

        if update_data:
            student = await student_service.update_student(student_id, StudentUpdate(**update_data))
        else:
            student = current_student

        if program_type is not None and program_type != student.program_type:
            await StudentProgramWorkflow(self.session).switch_program(
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
        sort_expression = sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
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
        teacher = await TeacherLifecycleWorkflow(self.session).update_teacher(
            teacher_id, teacher_in
        )
        user = await UserService(self.session).get_user(teacher.user_id)
        return AdminTeacherRead(teacher=teacher, user=user)


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
