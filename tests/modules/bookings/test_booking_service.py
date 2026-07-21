from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.exceptions import BadRequestError, ConflictError
from app.modules.bookings.service import BookingService
from app.modules.classes.models import ClassSession
from app.modules.students.models import Student
from app.shared.enums import ClassSessionStatus, StudentProgramType, StudentStatus


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
