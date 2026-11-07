from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import BadRequestError, ConflictError
from app.modules.bookings.cancellation_service import BookingCancellationService
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    BookingActionRequest,
    BookingAttendanceMark,
    ClassAttendanceMark,
)
from app.modules.bookings.service import _BookingOperations as BookingService
from app.modules.classes.models import ClassSession
from app.modules.schedules.models import TeacherAvailabilitySlot
from app.modules.students.models import Student
from app.shared.enums import (
    AvailabilitySlotSource,
    AvailabilitySlotStatus,
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    StudentProgramType,
    StudentStatus,
)


class FakeSession:
    def __init__(self, bookings=None, slot=None) -> None:
        self.bookings = bookings or []
        self.slot = slot
        self.scalars = AsyncMock(return_value=self.bookings)
        self.get = AsyncMock(return_value=slot)
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.added = []

    def add(self, value) -> None:
        self.added.append(value)


def test_student_can_book_when_active_and_access_window_is_current() -> None:
    student = Student(
        id=uuid4(),
        user_id=uuid4(),
        program_type=StudentProgramType.ONE_ON_ONE,
        status=StudentStatus.ACTIVE,
        access_starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        access_ends_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    BookingService(session=None)._ensure_student_can_book(
        student=student,
        expected_program_type=StudentProgramType.ONE_ON_ONE,
        now=datetime(2026, 7, 20, tzinfo=UTC),
    )


def test_student_cannot_book_when_program_type_does_not_match_flow() -> None:
    student = Student(
        id=uuid4(),
        user_id=uuid4(),
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ACTIVE,
        access_starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        access_ends_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    with pytest.raises(ConflictError, match="Student program type does not match"):
        BookingService(session=None)._ensure_student_can_book(
            student=student,
            expected_program_type=StudentProgramType.ONE_ON_ONE,
            now=datetime(2026, 7, 20, tzinfo=UTC),
        )


def test_student_cannot_book_when_access_window_is_expired() -> None:
    student = Student(
        id=uuid4(),
        user_id=uuid4(),
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ACTIVE,
        access_starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        access_ends_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    with pytest.raises(ConflictError, match="Student access window is not currently valid"):
        BookingService(session=None)._ensure_student_can_book(
            student=student,
            expected_program_type=StudentProgramType.BATCH,
            now=datetime(2026, 7, 20, tzinfo=UTC),
        )


def test_manual_admin_add_access_check_allows_any_program_type() -> None:
    student = Student(
        id=uuid4(),
        user_id=uuid4(),
        program_type=StudentProgramType.ONE_ON_ONE,
        status=StudentStatus.ACTIVE,
        access_starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        access_ends_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    BookingService(session=None)._ensure_student_has_active_access(
        student=student,
        now=datetime(2026, 7, 20, tzinfo=UTC),
    )


def test_manual_admin_add_access_check_rejects_inactive_student() -> None:
    student = Student(
        id=uuid4(),
        user_id=uuid4(),
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.PAUSED,
        access_starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        access_ends_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    with pytest.raises(ConflictError, match="Student is not active"):
        BookingService(session=None)._ensure_student_has_active_access(
            student=student,
            now=datetime(2026, 7, 20, tzinfo=UTC),
        )


def test_student_can_change_booking_exactly_twenty_four_hours_before_class() -> None:
    class_session = ClassSession(
        id=uuid4(),
        starts_at=datetime(2026, 7, 21, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 21, 11, 0, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
    )

    BookingService(session=None)._ensure_student_can_change_booking(
        class_session=class_session,
        now=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
    )


def test_student_cannot_change_booking_inside_twenty_four_hour_cutoff() -> None:
    class_session = ClassSession(
        id=uuid4(),
        starts_at=datetime(2026, 7, 21, 9, 59, tzinfo=UTC),
        ends_at=datetime(2026, 7, 21, 11, 0, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
    )

    with pytest.raises(ConflictError, match="Booking change window is closed"):
        BookingService(session=None)._ensure_student_can_change_booking(
            class_session=class_session,
            now=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        )


def test_student_cannot_change_started_booking() -> None:
    class_session = ClassSession(
        id=uuid4(),
        starts_at=datetime(2026, 7, 20, 9, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
    )

    with pytest.raises(BadRequestError, match="Cannot change a past or started booking"):
        BookingService(session=None)._ensure_student_can_change_booking(
            class_session=class_session,
            now=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        )


def test_booking_attendance_mark_rejects_non_attendance_status() -> None:
    with pytest.raises(ValidationError, match="attendance status must be attended or missed"):
        BookingAttendanceMark(status=BookingStatus.BOOKED)


def test_class_attendance_mark_rejects_duplicate_booking_ids() -> None:
    booking_id = uuid4()

    with pytest.raises(ValidationError, match="duplicate booking_id"):
        ClassAttendanceMark(
            records=[
                {"booking_id": booking_id, "status": BookingStatus.ATTENDED},
                {"booking_id": booking_id, "status": BookingStatus.MISSED},
            ]
        )


def test_attendance_can_be_marked_at_class_start() -> None:
    booking = Booking(
        id=uuid4(),
        student_id=uuid4(),
        class_session_id=uuid4(),
        status=BookingStatus.BOOKED,
    )
    class_session = ClassSession(
        id=booking.class_session_id,
        starts_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 11, 0, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
    )

    BookingService(session=None)._ensure_can_mark_attendance(
        booking=booking,
        class_session=class_session,
        now=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
    )


def test_attendance_cannot_be_marked_before_class_start() -> None:
    booking = Booking(
        id=uuid4(),
        student_id=uuid4(),
        class_session_id=uuid4(),
        status=BookingStatus.BOOKED,
    )
    class_session = ClassSession(
        id=booking.class_session_id,
        starts_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 11, 0, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
    )

    with pytest.raises(BadRequestError, match="Attendance can only be marked after class start"):
        BookingService(session=None)._ensure_can_mark_attendance(
            booking=booking,
            class_session=class_session,
            now=datetime(2026, 7, 20, 9, 59, tzinfo=UTC),
        )


def test_cancelled_booking_cannot_be_marked_for_attendance() -> None:
    booking = Booking(
        id=uuid4(),
        student_id=uuid4(),
        class_session_id=uuid4(),
        status=BookingStatus.CANCELLED,
    )
    class_session = ClassSession(
        id=booking.class_session_id,
        starts_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 11, 0, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
    )

    with pytest.raises(ConflictError, match="Cancelled bookings cannot be marked"):
        BookingService(session=None)._ensure_can_mark_attendance(
            booking=booking,
            class_session=class_session,
            now=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_admin_class_cancel_cancels_booked_bookings_and_reopens_future_one_on_one_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class_session = ClassSession(
        id=uuid4(),
        teacher_id=uuid4(),
        teacher_availability_slot_id=uuid4(),
        program_type=StudentProgramType.ONE_ON_ONE,
        starts_at=datetime(2026, 7, 23, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 23, 11, 0, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
        capacity=1,
    )
    booking = Booking(
        id=uuid4(),
        student_id=uuid4(),
        class_session_id=class_session.id,
        status=BookingStatus.BOOKED,
    )
    slot = TeacherAvailabilitySlot(
        id=class_session.teacher_availability_slot_id,
        teacher_id=class_session.teacher_id,
        rule_id=None,
        source=AvailabilitySlotSource.MANUAL,
        starts_at=class_session.starts_at,
        ends_at=class_session.ends_at,
        status=AvailabilitySlotStatus.BOOKED,
    )
    session = FakeSession(bookings=[booking], slot=slot)
    service = BookingCancellationService(session)

    async def fake_get_class_session_for_update(self, class_session_id):
        assert class_session_id == class_session.id
        return class_session

    monkeypatch.setattr(
        BookingCancellationService,
        "_get_class_session_for_update",
        fake_get_class_session_for_update,
    )
    monkeypatch.setattr(
        "app.modules.bookings.cancellation_service.utc_now",
        lambda: datetime(2026, 7, 22, tzinfo=UTC),
    )

    result = await service.admin_cancel_class_session(
        class_session.id,
        BookingActionRequest(reason="teacher unavailable"),
    )

    assert result is class_session
    assert class_session.status == ClassSessionStatus.CANCELLED
    assert booking.status == BookingStatus.CANCELLED
    assert slot.status == AvailabilitySlotStatus.AVAILABLE
    assert len(session.added) == 1
    assert session.added[0].booking_id == booking.id
    assert session.added[0].reason == "teacher unavailable"
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(class_session)


@pytest.mark.asyncio
async def test_teacher_class_cancel_only_cancels_selected_batch_option_bookings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teacher_user_id = uuid4()
    class_session = ClassSession(
        id=uuid4(),
        teacher_id=uuid4(),
        batch_group_id=uuid4(),
        batch_schedule_day_id=uuid4(),
        program_type=StudentProgramType.BATCH,
        display_label="Morning",
        starts_at=datetime(2026, 7, 23, 10, tzinfo=UTC),
        ends_at=datetime(2026, 7, 23, 11, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
        capacity=10,
    )
    selected_booking = Booking(
        id=uuid4(),
        student_id=uuid4(),
        class_session_id=class_session.id,
        status=BookingStatus.BOOKED,
    )
    other_option_booking = Booking(
        id=uuid4(),
        student_id=uuid4(),
        class_session_id=uuid4(),
        status=BookingStatus.BOOKED,
    )
    session = FakeSession(bookings=[selected_booking])
    service = BookingCancellationService(session)

    monkeypatch.setattr(
        BookingCancellationService,
        "_get_class_session_for_update",
        AsyncMock(return_value=class_session),
    )
    monkeypatch.setattr(BookingCancellationService, "_get_optional_user", AsyncMock())
    monkeypatch.setattr(
        "app.modules.bookings.cancellation_service.utc_now",
        lambda: datetime(2026, 7, 22, tzinfo=UTC),
    )

    await service.teacher_cancel_batch_class_session(
        class_session.id,
        BookingActionRequest(actor_user_id=teacher_user_id, reason="Unable to teach"),
    )

    assert class_session.status == ClassSessionStatus.CANCELLED
    assert selected_booking.status == BookingStatus.CANCELLED
    assert other_option_booking.status == BookingStatus.BOOKED
    assert len(session.added) == 1
    event = session.added[0]
    assert event.event_type == BookingEventType.CANCELLED_BY_TEACHER
    assert event.actor_user_id == teacher_user_id
    assert event.reason == "Unable to teach"
