from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import BadRequestError, ConflictError
from app.modules.batch_groups.models import BatchGroup
from app.modules.batch_schedule_days._shared import _BatchScheduleDayShared
from app.modules.batch_schedule_days.query_service import BatchScheduleDayQueryService
from app.modules.batch_schedule_days.schemas import (
    MAX_BATCH_DAY_OPTIONS,
    BatchDayOptionCreate,
    BatchDayOptionUpdate,
    BatchScheduleDayRead,
)
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.classes.models import ClassSession
from app.shared.enums import (
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    DayOfWeek,
    StudentProgramType,
)

DEFAULTS_ID = UUID("00000000-0000-0000-0000-000000000001")
DAY_TO_INDEX = {
    DayOfWeek.MONDAY: 0,
    DayOfWeek.TUESDAY: 1,
    DayOfWeek.WEDNESDAY: 2,
    DayOfWeek.THURSDAY: 3,
    DayOfWeek.FRIDAY: 4,
    DayOfWeek.SATURDAY: 5,
    DayOfWeek.SUNDAY: 6,
}
DEFAULT_TEMPLATES = [
    {"display_label": "Morning", "start_time_utc": "08:00:00", "duration_minutes": 60},
    {"display_label": "Noon", "start_time_utc": "12:00:00", "duration_minutes": 60},
    {"display_label": "Evening", "start_time_utc": "18:00:00", "duration_minutes": 60},
]


class BatchScheduleOptionService(_BatchScheduleDayShared):
    async def add_option(
        self,
        day_id: UUID,
        option_in: BatchDayOptionCreate,
    ) -> BatchScheduleDayRead:
        day = await self._get_day_model(day_id)
        if option_in.starts_at.date() != day.schedule_date:
            raise BadRequestError("option starts_at must fall on batch schedule date in UTC")
        sessions = await self._get_day_sessions(day_id)
        if len([value for value in sessions if value.status != ClassSessionStatus.CANCELLED]) >= (
            MAX_BATCH_DAY_OPTIONS
        ):
            raise ConflictError("Batch day already has the maximum number of options")
        await self._validate_option(
            day=day,
            option=option_in,
            existing_sessions=sessions,
        )
        batch_group = await self.session.get(BatchGroup, day.batch_group_id)
        class_session = ClassSession(
            teacher_id=option_in.teacher_id,
            teacher_availability_slot_id=None,
            batch_group_id=day.batch_group_id,
            batch_schedule_day_id=day.id,
            program_type=StudentProgramType.BATCH,
            batch_slot=None,
            display_label=option_in.display_label,
            option_order=max((value.option_order or 0 for value in sessions), default=0) + 1,
            starts_at=option_in.starts_at,
            ends_at=option_in.ends_at,
            status=ClassSessionStatus.SCHEDULED,
            capacity=option_in.capacity or batch_group.default_capacity,
        )
        self.session.add(class_session)
        await self.session.commit()
        return await BatchScheduleDayQueryService(self.session).get_day(day.id)

    async def update_option(
        self,
        day_id: UUID,
        class_session_id: UUID,
        option_in: BatchDayOptionUpdate,
        *,
        event_source: str = "admin",
    ) -> BatchScheduleDayRead:
        day = await self._get_day_model(day_id)
        await self._get_optional_user(option_in.actor_user_id)
        class_session = await self._get_day_session_for_update(day_id, class_session_id)
        if class_session.status != ClassSessionStatus.SCHEDULED:
            raise ConflictError("Only scheduled options can be updated")
        update_data = option_in.model_dump(
            exclude_unset=True,
            exclude={"reason", "actor_user_id"},
        )
        for field in ("display_label", "starts_at", "ends_at", "capacity"):
            if field in update_data and update_data[field] is None:
                raise BadRequestError(f"{field} cannot be null")
        starts_at = update_data.get("starts_at", class_session.starts_at)
        ends_at = update_data.get("ends_at", class_session.ends_at)
        if starts_at >= ends_at:
            raise BadRequestError("starts_at must be before ends_at")
        if starts_at.date() != day.schedule_date:
            raise BadRequestError("option starts_at must fall on batch schedule date in UTC")
        capacity = update_data.get("capacity", class_session.capacity)
        active_bookings = list(
            await self.session.scalars(
                select(Booking)
                .where(
                    Booking.class_session_id == class_session.id,
                    Booking.status == BookingStatus.BOOKED,
                )
                .with_for_update()
            )
        )
        active_count = len(active_bookings)
        if capacity < active_count:
            raise ConflictError("Capacity cannot be below active booking count")
        teacher_id = update_data.get("teacher_id", class_session.teacher_id)
        if "teacher_id" in option_in.model_fields_set and teacher_id is None:
            pass
        elif teacher_id is not None:
            await self._get_active_teacher(teacher_id)
        candidate = BatchDayOptionCreate(
            display_label=update_data.get("display_label", class_session.display_label),
            starts_at=starts_at,
            ends_at=ends_at,
            teacher_id=teacher_id,
            capacity=capacity,
        )
        await self._validate_option(
            day=day,
            option=candidate,
            existing_sessions=await self._get_day_sessions(day_id),
            exclude_session_id=class_session.id,
        )
        day_start = datetime.combine(starts_at.date(), time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        for booking in active_bookings:
            conflict = await self.session.scalar(
                select(Booking.id)
                .join(ClassSession, Booking.class_session_id == ClassSession.id)
                .where(
                    Booking.student_id == booking.student_id,
                    Booking.class_session_id != class_session.id,
                    Booking.status != BookingStatus.CANCELLED,
                    ClassSession.status != ClassSessionStatus.CANCELLED,
                    ClassSession.starts_at >= day_start,
                    ClassSession.starts_at < day_end,
                )
            )
            if conflict is not None:
                raise ConflictError(
                    "A booked student already has an active class on the destination UTC date"
                )
        schedule_changed = any(
            field in update_data for field in ("starts_at", "ends_at", "teacher_id", "capacity")
        )
        old_metadata = {
            "starts_at": class_session.starts_at.isoformat(),
            "ends_at": class_session.ends_at.isoformat(),
            "teacher_id": str(class_session.teacher_id) if class_session.teacher_id else None,
            "capacity": class_session.capacity,
        }
        new_metadata = {
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "teacher_id": str(teacher_id) if teacher_id else None,
            "capacity": capacity,
        }
        if schedule_changed:
            for booking in active_bookings:
                for event_type in (
                    BookingEventType.RESCHEDULED_FROM,
                    BookingEventType.RESCHEDULED_TO,
                ):
                    self.session.add(
                        BookingEvent(
                            booking_id=booking.id,
                            event_type=event_type,
                            actor_user_id=option_in.actor_user_id,
                            reason=option_in.reason or "batch-day option updated",
                            event_metadata={
                                "source": event_source,
                                "batch_schedule_day_id": str(day.id),
                                "old": old_metadata,
                                "new": new_metadata,
                            },
                        )
                    )
        for field, value in update_data.items():
            setattr(class_session, field, value)
        await self.session.commit()
        return await BatchScheduleDayQueryService(self.session).get_day(day.id)

    async def remove_option(
        self,
        day_id: UUID,
        class_session_id: UUID,
    ) -> BatchScheduleDayRead:
        class_session = await self._get_day_session_for_update(day_id, class_session_id)
        if await self._active_booking_count(class_session.id):
            raise ConflictError("Move or remove active students before removing this option")
        class_session.status = ClassSessionStatus.CANCELLED
        await self.session.commit()
        return await BatchScheduleDayQueryService(self.session).get_day(day_id)
