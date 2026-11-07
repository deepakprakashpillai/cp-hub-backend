from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.modules.notifications.service import NotificationService
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherUpdate
from app.modules.teachers.service import TeacherService


class TeacherLifecycleWorkflow:
    """Coordinates teacher profile changes that affect other domains."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def update_teacher(
        self,
        teacher_id: UUID,
        teacher_in: TeacherUpdate,
    ) -> Teacher:
        teacher = await TeacherService(self.session).get_teacher(teacher_id)
        was_active = teacher.is_active
        update_data = teacher_in.model_dump(exclude_unset=True)

        for non_nullable_field in ("display_name", "is_active"):
            if non_nullable_field in update_data and update_data[non_nullable_field] is None:
                raise BadRequestError(f"{non_nullable_field} cannot be null")

        for field, value in update_data.items():
            setattr(teacher, field, value)

        if update_data.get("is_active") is False:
            affected_students = list(
                await self.session.scalars(
                    select(Student).where(Student.assigned_teacher_id == teacher.id)
                )
            )
            await self.session.execute(
                update(Student)
                .where(Student.assigned_teacher_id == teacher.id)
                .values(assigned_teacher_id=None)
            )
            service = NotificationService(self.session)
            for student in affected_students:
                await service.emit_to_users(
                    event_type="student.teacher_assignment_removed",
                    aggregate_type="teacher",
                    aggregate_id=teacher.id,
                    dedupe_key=f"notification:teacher-deactivated:{teacher.id}:{student.id}",
                    recipient_user_ids=[student.user_id],
                    title="Your assigned teacher is unavailable",
                    body="Your permanent teacher assignment was removed.",
                    category="updates",
                    priority="high",
                    action_url="/student",
                    include_admins=True,
                )
        if was_active and update_data.get("is_active") is False:
            await NotificationService(self.session).emit_to_users(
                event_type="teacher.profile_paused",
                aggregate_type="teacher",
                aggregate_id=teacher.id,
                dedupe_key=f"notification:teacher-paused:{teacher.id}",
                recipient_user_ids=[teacher.user_id],
                title="Teacher profile paused",
                body="Your teacher profile is currently unavailable for new class assignments.",
                category="account",
                priority="high",
                action_url="/teacher/settings",
                include_admins=True,
            )

        await self.session.commit()
        await self.session.refresh(teacher)
        return teacher
