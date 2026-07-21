from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import BadRequestError, ConflictError
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import BookingAttendanceMark, ClassAttendanceMark
from app.modules.bookings.service import BookingService
from app.modules.classes.models import ClassSession
from app.modules.students.models import Student
from app.shared.enums import BookingStatus, ClassSessionStatus, StudentProgramType, StudentStatus


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
