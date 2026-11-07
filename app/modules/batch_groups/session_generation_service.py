from datetime import date
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import ConflictError
from app.modules.batch_groups._shared import _BatchGroupShared
from app.modules.batch_groups.lifecycle_service import BatchGroupLifecycleService
from app.modules.batch_groups.schemas import (
    BatchSessionBulkGenerate,
)
from app.modules.batch_schedule_days.models import BatchScheduleDay
from app.modules.classes.models import ClassSession
from app.shared.enums import (
    DayOfWeek,
)

DAY_TO_INDEX = {
    DayOfWeek.MONDAY: 0,
    DayOfWeek.TUESDAY: 1,
    DayOfWeek.WEDNESDAY: 2,
    DayOfWeek.THURSDAY: 3,
    DayOfWeek.FRIDAY: 4,
    DayOfWeek.SATURDAY: 5,
    DayOfWeek.SUNDAY: 6,
}


class BatchSessionGenerationService(_BatchGroupShared):
    async def generate_batch_sessions(
        self,
        batch_group_id: UUID,
        generation_in: BatchSessionBulkGenerate,
    ) -> list[ClassSession]:
        batch_group = await BatchGroupLifecycleService(self.session).get_batch_group(batch_group_id)
        if not batch_group.is_active:
            raise ConflictError("Cannot generate sessions for an inactive batch group")

        await self._validate_generation_teachers(generation_in.sessions)
        expected_sessions = self._build_expected_batch_sessions(batch_group, generation_in)
        self._ensure_no_overlaps_within_generation(expected_sessions)
        await self._ensure_no_existing_batch_session_overlaps(
            batch_group_id=batch_group.id,
            expected_sessions=expected_sessions,
        )

        day_by_date: dict[date, BatchScheduleDay] = {}
        for session_data in expected_sessions:
            schedule_date = session_data["starts_at"].date()
            if schedule_date in day_by_date:
                continue
            existing_day = await self.session.scalar(
                select(BatchScheduleDay.id).where(
                    BatchScheduleDay.batch_group_id == batch_group.id,
                    BatchScheduleDay.schedule_date == schedule_date,
                )
            )
            if existing_day is not None:
                raise ConflictError(
                    f"Batch schedule day already exists for {schedule_date.isoformat()}"
                )
            day = BatchScheduleDay(
                batch_group_id=batch_group.id,
                schedule_date=schedule_date,
                created_by_user_id=None,
            )
            self.session.add(day)
            day_by_date[schedule_date] = day
        await self.session.flush()

        class_sessions: list[ClassSession] = []
        option_order_by_date: dict[date, int] = {}
        for session_data in expected_sessions:
            schedule_date = session_data["starts_at"].date()
            option_order_by_date[schedule_date] = option_order_by_date.get(schedule_date, 0) + 1
            session_data["batch_schedule_day_id"] = day_by_date[schedule_date].id
            session_data["display_label"] = (
                session_data["batch_slot"].value.replace("_", " ").title()
            )
            session_data["option_order"] = option_order_by_date[schedule_date]
            class_session = ClassSession(**session_data)
            self.session.add(class_session)
            class_sessions.append(class_session)

        await self.session.commit()
        for class_session in class_sessions:
            await self.session.refresh(class_session)
        return class_sessions
