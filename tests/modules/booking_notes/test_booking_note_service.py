from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import BadRequestError
from app.core.pagination import Page, PaginationParams
from app.modules.booking_notes.models import BookingNote
from app.modules.booking_notes.schemas import BookingNoteCreate, BookingNoteUpdate
from app.modules.booking_notes.service import BookingNoteService
from app.modules.bookings.models import Booking
from app.modules.classes.models import ClassSession
from app.modules.teachers.models import Teacher
from app.shared.enums import BookingNoteVisibility


class FakeSession:
    def __init__(self) -> None:
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.added = []

    def add(self, value) -> None:
        self.added.append(value)


def test_booking_note_create_defaults_to_admin_only_and_trims_note() -> None:
    note_in = BookingNoteCreate(teacher_id=uuid4(), note="  Strong progress  ")

    assert note_in.note == "Strong progress"
    assert note_in.visibility == BookingNoteVisibility.ADMIN_ONLY


def test_booking_note_create_rejects_blank_note() -> None:
    with pytest.raises(ValidationError, match="note cannot be blank"):
        BookingNoteCreate(teacher_id=uuid4(), note="   ")


@pytest.mark.asyncio
async def test_teacher_creates_note_for_booking_they_taught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    service = BookingNoteService(session)
    teacher_id = uuid4()
    booking = Booking(
        id=uuid4(),
        student_id=uuid4(),
        class_session_id=uuid4(),
    )
    class_session = ClassSession(
        id=booking.class_session_id,
        teacher_id=teacher_id,
        starts_at=datetime(2026, 7, 24, 9, 0, tzinfo=UTC),
    )

    async def fake_get_booking_and_class_session(booking_id):
        assert booking_id == booking.id
        return booking, class_session

    async def fake_validate_teacher_ownership(received_teacher_id, received_class):
        assert received_teacher_id == teacher_id
        assert received_class is class_session

    monkeypatch.setattr(
        service,
        "_get_booking_and_class_session",
        fake_get_booking_and_class_session,
    )
    monkeypatch.setattr(
        service,
        "_validate_teacher_ownership",
        fake_validate_teacher_ownership,
    )
    monkeypatch.setattr(
        "app.modules.booking_notes.service.utc_now",
        lambda: datetime(2026, 7, 24, 10, 0, tzinfo=UTC),
    )

    created = await service.create_booking_note(
        booking.id,
        BookingNoteCreate(teacher_id=teacher_id, note="Good use of recursion."),
    )

    assert created.booking_id == booking.id
    assert created.class_session_id == class_session.id
    assert created.student_id == booking.student_id
    assert created.teacher_id == teacher_id
    assert created.note == "Good use of recursion."
    assert created.visibility == BookingNoteVisibility.ADMIN_ONLY
    assert session.added == [created]
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(created)


@pytest.mark.asyncio
async def test_teacher_cannot_create_note_before_class_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = BookingNoteService(FakeSession())
    teacher_id = uuid4()
    booking = Booking(
        id=uuid4(),
        student_id=uuid4(),
        class_session_id=uuid4(),
    )
    class_session = ClassSession(
        id=booking.class_session_id,
        teacher_id=teacher_id,
        starts_at=datetime(2026, 7, 24, 11, 0, tzinfo=UTC),
    )

    async def fake_get_booking_and_class_session(booking_id):
        return booking, class_session

    async def fake_validate_teacher_ownership(received_teacher_id, received_class):
        return None

    monkeypatch.setattr(
        service,
        "_get_booking_and_class_session",
        fake_get_booking_and_class_session,
    )
    monkeypatch.setattr(
        service,
        "_validate_teacher_ownership",
        fake_validate_teacher_ownership,
    )
    monkeypatch.setattr(
        "app.modules.booking_notes.service.utc_now",
        lambda: datetime(2026, 7, 24, 10, 59, tzinfo=UTC),
    )

    with pytest.raises(BadRequestError, match="only be created after class start"):
        await service.create_booking_note(
            booking.id,
            BookingNoteCreate(teacher_id=teacher_id, note="Too early"),
        )


@pytest.mark.asyncio
async def test_teacher_ownership_requires_class_teacher() -> None:
    teacher_id = uuid4()
    other_teacher_id = uuid4()
    teacher = Teacher(id=teacher_id, user_id=uuid4(), display_name="Teacher")
    session = FakeSession()
    session.get = AsyncMock(return_value=teacher)
    class_session = ClassSession(id=uuid4(), teacher_id=other_teacher_id)

    with pytest.raises(BadRequestError, match="not assigned to this class session"):
        await BookingNoteService(session)._validate_teacher_ownership(
            teacher_id,
            class_session,
        )


@pytest.mark.asyncio
async def test_teacher_lists_notes_for_owned_booking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = BookingNoteService(FakeSession())
    pagination = PaginationParams(page=1, page_size=25)
    teacher_id = uuid4()
    booking = Booking(id=uuid4(), student_id=uuid4(), class_session_id=uuid4())
    class_session = ClassSession(id=booking.class_session_id, teacher_id=teacher_id)
    expected = Page(items=[], total=0, page=1, page_size=25)

    async def fake_get_booking_and_class_session(booking_id):
        return booking, class_session

    async def fake_validate_teacher_ownership(received_teacher_id, received_class):
        assert received_teacher_id == teacher_id

    async def fake_list_booking_notes(booking_id, received_pagination):
        assert booking_id == booking.id
        assert received_pagination is pagination
        return expected

    monkeypatch.setattr(
        service,
        "_get_booking_and_class_session",
        fake_get_booking_and_class_session,
    )
    monkeypatch.setattr(
        service,
        "_validate_teacher_ownership",
        fake_validate_teacher_ownership,
    )
    monkeypatch.setattr(service, "_list_booking_notes", fake_list_booking_notes)

    result = await service.list_teacher_booking_notes(
        booking.id,
        teacher_id,
        pagination,
    )

    assert result is expected


@pytest.mark.asyncio
async def test_teacher_cannot_update_another_teachers_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = BookingNoteService(FakeSession())
    booking_note = BookingNote(
        id=uuid4(),
        booking_id=uuid4(),
        class_session_id=uuid4(),
        student_id=uuid4(),
        teacher_id=uuid4(),
        note="Original",
        visibility=BookingNoteVisibility.ADMIN_ONLY,
    )

    async def fake_get_booking_note(note_id):
        return booking_note

    monkeypatch.setattr(service, "_get_booking_note", fake_get_booking_note)

    with pytest.raises(BadRequestError, match="does not own"):
        await service.update_booking_note(
            booking_note.id,
            uuid4(),
            BookingNoteUpdate(note="Changed"),
        )


@pytest.mark.asyncio
async def test_teacher_updates_owned_booking_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    service = BookingNoteService(session)
    teacher_id = uuid4()
    booking_note = BookingNote(
        id=uuid4(),
        booking_id=uuid4(),
        class_session_id=uuid4(),
        student_id=uuid4(),
        teacher_id=teacher_id,
        note="Original",
        visibility=BookingNoteVisibility.ADMIN_ONLY,
    )
    booking = Booking(
        id=booking_note.booking_id,
        student_id=booking_note.student_id,
        class_session_id=booking_note.class_session_id,
    )
    class_session = ClassSession(
        id=booking_note.class_session_id,
        teacher_id=teacher_id,
    )

    async def fake_get_booking_note(note_id):
        return booking_note

    async def fake_get_booking_and_class_session(booking_id):
        return booking, class_session

    async def fake_validate_teacher_ownership(received_teacher_id, received_class):
        return None

    monkeypatch.setattr(service, "_get_booking_note", fake_get_booking_note)
    monkeypatch.setattr(
        service,
        "_get_booking_and_class_session",
        fake_get_booking_and_class_session,
    )
    monkeypatch.setattr(
        service,
        "_validate_teacher_ownership",
        fake_validate_teacher_ownership,
    )

    updated = await service.update_booking_note(
        booking_note.id,
        teacher_id,
        BookingNoteUpdate(
            note="Updated feedback",
            visibility=BookingNoteVisibility.STUDENT_VISIBLE,
        ),
    )

    assert updated.note == "Updated feedback"
    assert updated.visibility == BookingNoteVisibility.STUDENT_VISIBLE
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(booking_note)
