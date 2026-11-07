from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.batch_groups.service import BatchMembershipService
from app.modules.bookings.service import BookingCancellationService
from app.modules.notifications.service import NotificationService
from app.modules.students.models import StudentProgramChange
from app.modules.students.schemas import StudentProgramSwitch
from app.modules.students.service import StudentService
from app.modules.users.models import User
from app.shared.enums import StudentProgramType


class StudentProgramWorkflow:
    """Coordinates the cross-domain effects of changing a student's program."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def switch_program(
        self,
        student_id: UUID,
        switch_in: StudentProgramSwitch,
    ) -> StudentProgramChange:
        student = await StudentService(self.session).get_student(student_id)
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
        if switch_in.new_program_type == StudentProgramType.BATCH:
            student.assigned_teacher_id = None

        self.session.add(change)
        await self.session.flush()
        cancelled_count = await BookingCancellationService(
            self.session
        ).cancel_future_bookings_for_student(
            student_id=student.id,
            commit=False,
        )
        if switch_in.new_program_type == StudentProgramType.ONE_ON_ONE:
            await BatchMembershipService(self.session).end_active_student_membership(
                student_id=student.id,
                reason=switch_in.reason,
                commit=False,
            )
        await NotificationService(self.session).emit_to_users(
            event_type="student.program_changed",
            aggregate_type="student",
            aggregate_id=student.id,
            dedupe_key=f"notification:program-change:{change.id}",
            recipient_user_ids=[student.user_id],
            title="Your learning program changed",
            body=(
                "Your learning program was updated."
                if cancelled_count == 0
                else (
                    "Your learning program was updated and "
                    f"{cancelled_count} future class bookings changed."
                )
            ),
            category="updates",
            priority="high",
            action_url="/student/classes",
            data={
                "student_id": str(student.id),
                "previous_program": change.old_program_type.value,
                "current_program": change.new_program_type.value,
                "affected_booking_count": cancelled_count,
            },
            actor_user_id=switch_in.changed_by_user_id,
            include_admins=True,
        )
        await self.session.commit()
        await self.session.refresh(change)
        return change
