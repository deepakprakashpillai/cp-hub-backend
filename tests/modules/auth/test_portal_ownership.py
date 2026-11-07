from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import ConflictError
from app.modules.bookings.models import Booking
from app.modules.classes.models import ClassSession
from app.modules.portal.schemas import TeacherClassScheduleUpdate
from app.modules.portal.student_routes import _student_booking
from app.modules.portal.teacher_routes import (
    _teacher_class,
    update_my_batch_class_schedule,
)
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.shared.enums import ClassSessionStatus, StudentProgramType


@pytest.mark.asyncio
async def test_student_booking_helper_rejects_another_students_booking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    student = Student(id=uuid4(), user_id=uuid4(), program_type=StudentProgramType.BATCH)
    other_booking = Booking(id=uuid4(), student_id=uuid4(), class_session_id=uuid4())

    async def get_booking(_self, booking_id):
        assert booking_id == other_booking.id
        return other_booking

    monkeypatch.setattr(
        "app.modules.portal.student_routes.BookingQueryService.get_booking",
        get_booking,
    )

    with pytest.raises(HTTPException) as exc:
        await _student_booking(AsyncMock(), student, other_booking.id)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_teacher_class_helper_rejects_another_teachers_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teacher = Teacher(id=uuid4(), user_id=uuid4(), display_name="Teacher")
    other_class = ClassSession(id=uuid4(), teacher_id=uuid4())

    monkeypatch.setattr(
        "app.modules.portal.teacher_routes.ClassSessionService.get_class_session",
        AsyncMock(return_value=other_class),
    )

    with pytest.raises(HTTPException) as exc:
        await _teacher_class(AsyncMock(), teacher, other_class.id)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_teacher_schedule_uses_assigned_option_and_preserves_conflict_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teacher = Teacher(id=uuid4(), user_id=uuid4(), display_name="Teacher")
    class_session = ClassSession(
        id=uuid4(),
        teacher_id=teacher.id,
        batch_group_id=uuid4(),
        batch_schedule_day_id=uuid4(),
        program_type=StudentProgramType.BATCH,
        display_label="Morning",
        starts_at=datetime(2026, 8, 3, 9, tzinfo=UTC),
        ends_at=datetime(2026, 8, 3, 10, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
        capacity=10,
    )
    update_option = AsyncMock(side_effect=ConflictError("Batch-day options cannot overlap"))
    monkeypatch.setattr(
        "app.modules.portal.teacher_routes._teacher_class",
        AsyncMock(return_value=class_session),
    )
    monkeypatch.setattr(
        "app.modules.portal.teacher_routes.BatchScheduleOptionService.update_option",
        update_option,
    )
    monkeypatch.setattr(
        "app.modules.portal.teacher_routes.utc_now",
        lambda: datetime(2026, 8, 1, tzinfo=UTC),
    )

    with pytest.raises(ConflictError, match="cannot overlap"):
        await update_my_batch_class_schedule(
            class_session.id,
            TeacherClassScheduleUpdate(
                starts_at=datetime(2026, 8, 3, 10, tzinfo=UTC),
                ends_at=datetime(2026, 8, 3, 11, tzinfo=UTC),
                reason="Move later",
            ),
            AsyncMock(),
            teacher,
        )

    args, kwargs = update_option.await_args
    assert args[:2] == (class_session.batch_schedule_day_id, class_session.id)
    assert args[2].actor_user_id == teacher.user_id
    assert args[2].reason == "Move later"
    assert kwargs["event_source"] == "teacher"
