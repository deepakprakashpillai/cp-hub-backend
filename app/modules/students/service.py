from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.notifications.service import NotificationService
from app.modules.students.models import Student, StudentProgramChange
from app.modules.students.schemas import StudentCreate, StudentUpdate
from app.modules.teachers.models import Teacher
from app.modules.users.models import User
from app.shared.enums import StudentProgramType, StudentStatus, UserRole


class StudentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_students(self, pagination: PaginationParams) -> Page:
        return await paginate_scalars(
            self.session,
            select(Student).order_by(Student.created_at.desc()),
            pagination,
        )

    async def get_student(self, student_id: UUID) -> Student:
        student = await self.session.get(Student, student_id)
        if student is None:
            raise NotFoundError("Student not found")
        return student

    async def create_student(self, student_in: StudentCreate, *, commit: bool = True) -> Student:
        user = await self.session.get(User, student_in.user_id)
        if user is None:
            raise NotFoundError("User not found")

        if UserRole.STUDENT not in user.roles:
            raise ConflictError("Student profile can only be created for a student user")

        existing_student = await self.session.scalar(
            select(Student).where(Student.user_id == student_in.user_id)
        )
        if existing_student is not None:
            raise ConflictError("Student profile already exists for this user")

        self._validate_active_access_window(
            status=student_in.status,
            access_starts_at=student_in.access_starts_at,
            access_ends_at=student_in.access_ends_at,
        )

        student = Student(**student_in.model_dump())
        self.session.add(student)
        if commit:
            await self.session.commit()
            await self.session.refresh(student)
        else:
            await self.session.flush()
        return student

    async def update_student(self, student_id: UUID, student_in: StudentUpdate) -> Student:
        student = await self.get_student(student_id)
        previous_status = student.status
        update_data = student_in.model_dump(exclude_unset=True)

        for non_nullable_field in ("program_type", "status"):
            if non_nullable_field in update_data and update_data[non_nullable_field] is None:
                raise BadRequestError(f"{non_nullable_field} cannot be null")

        final_status = update_data.get("status", student.status)
        final_access_starts_at = update_data.get("access_starts_at", student.access_starts_at)
        final_access_ends_at = update_data.get("access_ends_at", student.access_ends_at)
        self._validate_active_access_window(
            status=final_status,
            access_starts_at=final_access_starts_at,
            access_ends_at=final_access_ends_at,
        )

        if (
            final_access_starts_at is not None
            and final_access_ends_at is not None
            and final_access_starts_at >= final_access_ends_at
        ):
            raise BadRequestError("access_starts_at must be before access_ends_at")

        for field, value in update_data.items():
            setattr(student, field, value)

        if "status" in update_data and previous_status != student.status:
            restricted = student.status in {
                StudentStatus.PAUSED,
                StudentStatus.COMPLETED,
                StudentStatus.CANCELLED,
            }
            await NotificationService(self.session).emit_to_users(
                event_type="student.status_changed",
                aggregate_type="student",
                aggregate_id=student.id,
                dedupe_key=f"notification:student-status:{student.id}:{student.status.value}",
                recipient_user_ids=[student.user_id],
                title="Student status updated",
                body=(
                    "Your learning access status has changed."
                    if restricted
                    else "Your student profile is now active."
                ),
                category="account",
                priority="high" if restricted else "medium",
                action_url="/student",
                data={
                    "student_id": str(student.id),
                    "previous_status": previous_status.value,
                    "current_status": student.status.value,
                },
                include_admins=True,
            )

        await self.session.commit()
        await self.session.refresh(student)
        return student

    async def set_assigned_teacher(
        self,
        student_id: UUID,
        assigned_teacher_id: UUID | None,
    ) -> Student:
        student = await self.get_student(student_id)
        previous_teacher_id = student.assigned_teacher_id
        if (
            assigned_teacher_id is not None
            and student.program_type != StudentProgramType.ONE_ON_ONE
        ):
            raise BadRequestError("Assigned teacher is only valid for one-on-one students")

        if assigned_teacher_id is not None:
            teacher = await self.session.get(Teacher, assigned_teacher_id)
            if teacher is None:
                raise NotFoundError("Teacher not found")
            if not teacher.is_active:
                raise BadRequestError("Assigned teacher must be active")

        student.assigned_teacher_id = assigned_teacher_id
        service = NotificationService(self.session)
        if previous_teacher_id != assigned_teacher_id:
            await service.emit_to_users(
                event_type="student.teacher_assignment_changed",
                aggregate_type="student",
                aggregate_id=student.id,
                dedupe_key=(
                    "notification:student-teacher:"
                    f"{student.id}:{assigned_teacher_id or 'unassigned'}"
                ),
                recipient_user_ids=[student.user_id],
                title="Your assigned teacher changed",
                body=(
                    "Your permanent teacher assignment was removed."
                    if assigned_teacher_id is None
                    else "A teacher has been assigned to your one-on-one learning."
                ),
                category="updates",
                priority="high" if assigned_teacher_id is None else "medium",
                action_url="/student",
                data={
                    "student_id": str(student.id),
                    "teacher_id": str(assigned_teacher_id) if assigned_teacher_id else None,
                    "teacher_name": teacher.display_name
                    if assigned_teacher_id is not None
                    else None,
                    "assignment_status": "assigned"
                    if assigned_teacher_id is not None
                    else "removed",
                },
                include_admins=True,
            )
            if assigned_teacher_id is not None:
                teacher = await self.session.get(Teacher, assigned_teacher_id)
                if teacher is not None:
                    await service.emit_to_users(
                        event_type="teacher.student_assignment_changed",
                        aggregate_type="student",
                        aggregate_id=student.id,
                        dedupe_key=f"notification:teacher-assignment:{student.id}:{teacher.id}",
                        recipient_user_ids=[teacher.user_id],
                        title="Student assignment updated",
                        body="A student has been assigned to your one-on-one roster.",
                        category="updates",
                        priority="medium",
                        action_url="/teacher/students",
                        data={
                            "student_id": str(student.id),
                            "student_name": (
                                await self.session.get(User, student.user_id)
                            ).full_name,
                            "teacher_id": str(teacher.id),
                        },
                    )
        await self.session.commit()
        await self.session.refresh(student)
        return student

    async def list_program_changes(
        self,
        pagination: PaginationParams,
        student_id: UUID | None = None,
    ) -> Page:
        query = select(StudentProgramChange).order_by(StudentProgramChange.created_at.desc())
        if student_id is not None:
            query = query.where(StudentProgramChange.student_id == student_id)

        return await paginate_scalars(self.session, query, pagination)

    def _validate_active_access_window(
        self,
        *,
        status: StudentStatus,
        access_starts_at,
        access_ends_at,
    ) -> None:
        if status == StudentStatus.ACTIVE and (access_starts_at is None or access_ends_at is None):
            raise BadRequestError("Active students must have access start and end datetimes")
