from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError
from app.modules.batch_groups.models import StudentBatchMembership
from app.modules.batch_schedule_days.models import BatchScheduleDay
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.bookings.service import _BookingOperations as BookingService
from app.modules.classes.models import ClassSession
from app.modules.students.models import Student
from app.shared.enums import (
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    StudentProgramType,
    StudentStatus,
)


class SelectionSession:
    def __init__(self, *, scalar_results, day) -> None:
        self.scalar = AsyncMock(side_effect=scalar_results)
        self.get = AsyncMock(return_value=day)
        self.flush = AsyncMock()
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.added = []

    def add(self, value) -> None:
        self.added.append(value)


def _selection_records(now: datetime):
    group_id = uuid4()
    day = BatchScheduleDay(
        id=uuid4(),
        batch_group_id=group_id,
        schedule_date=date(2026, 8, 3),
    )
    student = Student(
        id=uuid4(),
        user_id=uuid4(),
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ACTIVE,
        access_starts_at=now - timedelta(days=1),
        access_ends_at=now + timedelta(days=30),
    )
    membership = StudentBatchMembership(
        id=uuid4(),
        student_id=student.id,
        batch_group_id=group_id,
        is_active=True,
        assigned_at=now,
    )
    class_session = ClassSession(
        id=uuid4(),
        batch_group_id=group_id,
        batch_schedule_day_id=day.id,
        program_type=StudentProgramType.BATCH,
        starts_at=datetime(2026, 8, 3, 8, tzinfo=UTC),
        ends_at=datetime(2026, 8, 3, 9, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
        capacity=2,
    )
    return day, student, membership, class_session


@pytest.mark.asyncio
async def test_student_selects_one_batch_day_option_with_audited_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    day, student, membership, class_session = _selection_records(now)
    session = SelectionSession(
        scalar_results=[student, membership, None, None, 0],
        day=day,
    )
    service = BookingService(session)
    monkeypatch.setattr("app.modules.bookings.creation_service.utc_now", lambda: now)
    monkeypatch.setattr(
        service,
        "_get_class_session_for_update",
        AsyncMock(return_value=class_session),
    )

    booking, moved_from = await service.select_batch_day_option(
        student_id=student.id,
        batch_schedule_day_id=day.id,
        class_session_id=class_session.id,
        admin_override=False,
        actor_user_id=None,
        reason=None,
    )

    assert moved_from is None
    assert booking.student_id == student.id
    event = next(value for value in session.added if isinstance(value, BookingEvent))
    assert event.event_type == BookingEventType.SELECTED_BY_STUDENT
    assert event.actor_user_id == student.user_id
    assert event.event_metadata["source"] == "student"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_student_cannot_select_second_option_for_batch_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    day, student, membership, class_session = _selection_records(now)
    existing = Booking(
        id=uuid4(),
        student_id=student.id,
        class_session_id=uuid4(),
        status=BookingStatus.BOOKED,
        booked_at=now,
    )
    session = SelectionSession(
        scalar_results=[student, membership, existing],
        day=day,
    )
    service = BookingService(session)
    monkeypatch.setattr("app.modules.bookings.creation_service.utc_now", lambda: now)
    monkeypatch.setattr(
        service,
        "_get_class_session_for_update",
        AsyncMock(return_value=class_session),
    )

    with pytest.raises(ConflictError, match="already selected an option"):
        await service.select_batch_day_option(
            student_id=student.id,
            batch_schedule_day_id=day.id,
            class_session_id=class_session.id,
            admin_override=False,
            actor_user_id=None,
            reason=None,
        )

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_move_cancels_old_booking_and_creates_new_one_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    day, student, membership, class_session = _selection_records(now)
    existing = Booking(
        id=uuid4(),
        student_id=student.id,
        class_session_id=uuid4(),
        status=BookingStatus.BOOKED,
        booked_at=now,
    )
    session = SelectionSession(
        scalar_results=[student, membership, existing, None, 0],
        day=day,
    )
    service = BookingService(session)
    monkeypatch.setattr("app.modules.bookings.creation_service.utc_now", lambda: now)
    monkeypatch.setattr(
        service,
        "_get_class_session_for_update",
        AsyncMock(return_value=class_session),
    )

    booking, moved_from = await service.select_batch_day_option(
        student_id=student.id,
        batch_schedule_day_id=day.id,
        class_session_id=class_session.id,
        admin_override=True,
        actor_user_id=None,
        reason="admin override",
    )

    assert moved_from == existing.id
    assert existing.status == BookingStatus.CANCELLED
    assert booking.class_session_id == class_session.id
    events = [value for value in session.added if isinstance(value, BookingEvent)]
    assert [event.event_type for event in events] == [
        BookingEventType.MOVED_BY_ADMIN,
        BookingEventType.MOVED_BY_ADMIN,
    ]
    session.commit.assert_awaited_once()
