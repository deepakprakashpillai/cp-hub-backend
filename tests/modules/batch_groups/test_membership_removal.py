from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundError
from app.modules.batch_groups.models import BatchGroup, StudentBatchMembership
from app.modules.batch_groups.service import BatchGroupService
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.students.models import Student
from app.shared.enums import BookingEventType, BookingStatus, StudentProgramType, StudentStatus


class RemovalSession:
    def __init__(self, *, batch_group, student, membership, bookings) -> None:
        self.get = AsyncMock(side_effect=[batch_group, student])
        self.scalar = AsyncMock(return_value=membership)
        self.scalars = AsyncMock(return_value=bookings)
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.added = []

    def add(self, value) -> None:
        self.added.append(value)


@pytest.mark.asyncio
async def test_remove_student_ends_membership_and_cancels_future_group_bookings() -> None:
    batch_group_id = uuid4()
    student_id = uuid4()
    membership = StudentBatchMembership(
        id=uuid4(),
        student_id=student_id,
        batch_group_id=batch_group_id,
        is_active=True,
        assigned_at=datetime.now(UTC) - timedelta(days=30),
    )
    student = Student(
        id=student_id,
        user_id=uuid4(),
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ACTIVE,
    )
    booking = Booking(
        id=uuid4(),
        student_id=student_id,
        class_session_id=uuid4(),
        status=BookingStatus.BOOKED,
        booked_at=datetime.now(UTC),
    )
    session = RemovalSession(
        batch_group=BatchGroup(id=batch_group_id, name="Batch A", default_capacity=12),
        student=student,
        membership=membership,
        bookings=[booking],
    )

    result = await BatchGroupService(session).remove_student_from_batch_group(
        batch_group_id,
        student_id,
        reason="schedule changed",
    )

    assert result is membership
    assert membership.is_active is False
    assert membership.ended_at is not None
    assert membership.end_reason == "schedule changed"
    assert booking.status == BookingStatus.CANCELLED
    assert student.program_type == StudentProgramType.BATCH
    event = next(value for value in session.added if isinstance(value, BookingEvent))
    assert event.event_type == BookingEventType.CANCELLED_BY_ADMIN
    assert event.reason == "schedule changed"
    assert event.event_metadata["batch_group_id"] == str(batch_group_id)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_student_without_active_membership_does_not_commit() -> None:
    batch_group_id = uuid4()
    student_id = uuid4()
    student = Student(
        id=student_id,
        user_id=uuid4(),
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ACTIVE,
    )
    session = RemovalSession(
        batch_group=BatchGroup(id=batch_group_id, name="Batch A", default_capacity=12),
        student=student,
        membership=None,
        bookings=[],
    )

    with pytest.raises(NotFoundError, match="Active batch membership not found"):
        await BatchGroupService(session).remove_student_from_batch_group(
            batch_group_id,
            student_id,
            reason=None,
        )

    session.commit.assert_not_awaited()
