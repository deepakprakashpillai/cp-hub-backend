from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.students.schemas import StudentCreate
from app.shared.enums import StudentProgramType


def test_student_create_normalizes_access_datetimes_to_utc() -> None:
    student = StudentCreate(
        user_id=uuid4(),
        program_type=StudentProgramType.ONE_ON_ONE,
        access_starts_at=datetime.fromisoformat("2026-07-20T00:00:00+05:30"),
        access_ends_at=datetime.fromisoformat("2026-08-19T00:00:00+05:30"),
    )

    assert student.access_starts_at == datetime(2026, 7, 19, 18, 30, tzinfo=UTC)
    assert student.access_ends_at == datetime(2026, 8, 18, 18, 30, tzinfo=UTC)


def test_student_create_rejects_naive_access_datetime() -> None:
    with pytest.raises(ValidationError, match="datetime must include timezone info"):
        StudentCreate(
            user_id=uuid4(),
            program_type=StudentProgramType.BATCH,
            access_starts_at=datetime(2026, 7, 20),
        )


def test_student_create_rejects_invalid_access_window() -> None:
    with pytest.raises(ValidationError, match="access_starts_at must be before access_ends_at"):
        StudentCreate(
            user_id=uuid4(),
            program_type=StudentProgramType.BATCH,
            access_starts_at=datetime(2026, 7, 20, tzinfo=UTC),
            access_ends_at=datetime(2026, 7, 20, tzinfo=UTC),
        )
