from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.bookings.service import BookingService
from app.modules.students.models import Student, StudentProgramChange
from app.modules.students.schemas import StudentCreate, StudentProgramSwitch, StudentUpdate
from app.modules.users.models import User
from app.shared.enums import StudentStatus, UserRole


class StudentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_students(self) -> list[Student]:
        result = await self.session.scalars(select(Student).order_by(Student.created_at.desc()))
        return list(result)

    async def get_student(self, student_id: UUID) -> Student:
        student = await self.session.get(Student, student_id)
        if student is None:
            raise NotFoundError("Student not found")
        return student

    async def create_student(self, student_in: StudentCreate) -> Student:
        user = await self.session.get(User, student_in.user_id)
        if user is None:
            raise NotFoundError("User not found")

        if user.role != UserRole.STUDENT:
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
        await self.session.commit()
        await self.session.refresh(student)
        return student

    async def update_student(self, student_id: UUID, student_in: StudentUpdate) -> Student:
        student = await self.get_student(student_id)
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

        await self.session.commit()
        await self.session.refresh(student)
        return student

    async def switch_program(
        self,
        student_id: UUID,
        switch_in: StudentProgramSwitch,
    ) -> StudentProgramChange:
        student = await self.get_student(student_id)
        if student.program_type == switch_in.new_program_type:
            raise BadRequestError("Student is already in this program")

        if switch_in.changed_by_user_id is not None:
            user = await self.session.get(User, switch_in.changed_by_user_id)
            if user is None:
                raise NotFoundError("User not found")

        change = StudentProgramChange(
            student_id=student.id,
            old_program_type=student.program_type,
            new_program_type=switch_in.new_program_type,
            changed_by_user_id=switch_in.changed_by_user_id,
            reason=switch_in.reason,
        )
        student.program_type = switch_in.new_program_type

        self.session.add(change)
        await BookingService(self.session).cancel_future_bookings_for_student(
            student_id=student.id,
            commit=False,
        )
        await self.session.commit()
        await self.session.refresh(change)
        return change

    async def list_program_changes(
        self,
        student_id: UUID | None = None,
    ) -> list[StudentProgramChange]:
        query = select(StudentProgramChange).order_by(StudentProgramChange.created_at.desc())
        if student_id is not None:
            query = query.where(StudentProgramChange.student_id == student_id)

        result = await self.session.scalars(query)
        return list(result)

    def _validate_active_access_window(
        self,
        *,
        status: StudentStatus,
        access_starts_at,
        access_ends_at,
    ) -> None:
        if status == StudentStatus.ACTIVE and (
            access_starts_at is None or access_ends_at is None
        ):
            raise BadRequestError("Active students must have access start and end datetimes")
