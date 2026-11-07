from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError
from app.modules.admin.schemas import AdminBatchClassReschedule
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.bookings.service import _BookingOperations as BookingService
from app.modules.classes.models import ClassSession
from app.shared.enums import (
    BatchSlot,
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    StudentProgramType,
)


class RescheduleSession:
    def __init__(self, *, bookings, scalar_results) -> None:
        self.scalar = AsyncMock(side_effect=scalar_results)
        self.scalars = AsyncMock(return_value=bookings)
        self.get = AsyncMock()
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.added = []

    def add(self, value) -> None:
        self.added.append(value)


def _batch_class(now: datetime) -> ClassSession:
    return ClassSession(
        id=uuid4(),
        batch_group_id=uuid4(),
        teacher_id=None,
        teacher_availability_slot_id=None,
        program_type=StudentProgramType.BATCH,
        batch_slot=BatchSlot.MORNING,
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=1),
        status=ClassSessionStatus.SCHEDULED,
        capacity=3,
    )


@pytest.mark.asyncio
async def test_batch_class_reschedule_preserves_bookings_and_logs_timing_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    class_session = _batch_class(now)
    bookings = [
        Booking(
            id=uuid4(),
            student_id=uuid4(),
            class_session_id=class_session.id,
            status=BookingStatus.BOOKED,
            booked_at=now,
        ),
        Booking(
            id=uuid4(),
            student_id=uuid4(),
            class_session_id=class_session.id,
            status=BookingStatus.BOOKED,
            booked_at=now,
        ),
    ]
    session = RescheduleSession(
        bookings=bookings,
        scalar_results=[None] * 12,
    )
    service = BookingService(session)
    monkeypatch.setattr("app.modules.bookings.reschedule_service.utc_now", lambda: now)
    monkeypatch.setattr(service, "_get_optional_user", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service,
        "_get_class_session_for_update",
        AsyncMock(return_value=class_session),
    )
    new_start = now + timedelta(days=3)
    request = AdminBatchClassReschedule(
        starts_at=new_start,
        ends_at=new_start + timedelta(hours=1),
        batch_slot=BatchSlot.NOON,
        capacity=2,
        reason="holiday adjustment",
    )
    original_booking_ids = [booking.id for booking in bookings]

    result = await service.admin_reschedule_batch_class_session(
        class_session.id,
        request,
    )

    assert [booking.id for booking in result] == original_booking_ids
    assert class_session.starts_at == new_start
    assert class_session.batch_slot == BatchSlot.NOON
    assert class_session.capacity == 2
    events = [value for value in session.added if isinstance(value, BookingEvent)]
    assert len(events) == 4
    assert [event.event_type for event in events] == [
        BookingEventType.RESCHEDULED_FROM,
        BookingEventType.RESCHEDULED_TO,
        BookingEventType.RESCHEDULED_FROM,
        BookingEventType.RESCHEDULED_TO,
    ]
    assert events[0].event_metadata["old"]["starts_at"] == (now + timedelta(days=2)).isoformat()
    assert events[0].event_metadata["new"]["starts_at"] == new_start.isoformat()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_class_reschedule_capacity_conflict_does_not_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    class_session = _batch_class(now)
    bookings = [
        Booking(
            id=uuid4(),
            student_id=uuid4(),
            class_session_id=class_session.id,
            status=BookingStatus.BOOKED,
            booked_at=now,
        ),
        Booking(
            id=uuid4(),
            student_id=uuid4(),
            class_session_id=class_session.id,
            status=BookingStatus.BOOKED,
            booked_at=now,
        ),
    ]
    session = RescheduleSession(bookings=bookings, scalar_results=[None])
    service = BookingService(session)
    monkeypatch.setattr("app.modules.bookings.reschedule_service.utc_now", lambda: now)
    monkeypatch.setattr(service, "_get_optional_user", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service,
        "_get_class_session_for_update",
        AsyncMock(return_value=class_session),
    )
    request = AdminBatchClassReschedule(
        starts_at=now + timedelta(days=3),
        ends_at=now + timedelta(days=3, hours=1),
        capacity=1,
    )

    with pytest.raises(ConflictError, match="active booking count"):
        await service.admin_reschedule_batch_class_session(class_session.id, request)

    session.commit.assert_not_awaited()
    assert class_session.starts_at == now + timedelta(days=2)
    assert not session.added


@pytest.mark.asyncio
async def test_batch_class_reschedule_rejects_teacher_overlap_without_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    class_session = _batch_class(now)
    session = RescheduleSession(bookings=[], scalar_results=[uuid4()])
    session.get.return_value = object()
    service = BookingService(session)
    monkeypatch.setattr("app.modules.bookings.reschedule_service.utc_now", lambda: now)
    monkeypatch.setattr(service, "_get_optional_user", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service,
        "_get_class_session_for_update",
        AsyncMock(return_value=class_session),
    )
    request = AdminBatchClassReschedule(
        starts_at=now + timedelta(days=3),
        ends_at=now + timedelta(days=3, hours=1),
        teacher_id=uuid4(),
    )

    with pytest.raises(ConflictError, match="Teacher already has an overlapping"):
        await service.admin_reschedule_batch_class_session(class_session.id, request)

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_class_reschedule_rejects_student_daily_conflict_without_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    class_session = _batch_class(now)
    booking = Booking(
        id=uuid4(),
        student_id=uuid4(),
        class_session_id=class_session.id,
        status=BookingStatus.BOOKED,
        booked_at=now,
    )
    session = RescheduleSession(
        bookings=[booking],
        scalar_results=[None, uuid4()],
    )
    service = BookingService(session)
    monkeypatch.setattr("app.modules.bookings.reschedule_service.utc_now", lambda: now)
    monkeypatch.setattr(service, "_get_optional_user", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service,
        "_get_class_session_for_update",
        AsyncMock(return_value=class_session),
    )
    request = AdminBatchClassReschedule(
        starts_at=now + timedelta(days=3),
        ends_at=now + timedelta(days=3, hours=1),
    )

    with pytest.raises(ConflictError, match="booked student already has"):
        await service.admin_reschedule_batch_class_session(class_session.id, request)

    session.commit.assert_not_awaited()
    assert class_session.starts_at == now + timedelta(days=2)
