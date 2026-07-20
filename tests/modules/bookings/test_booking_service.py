from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError
from app.modules.bookings.service import BookingService
from app.modules.students.models import Student
from app.shared.enums import StudentProgramType, StudentStatus


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
