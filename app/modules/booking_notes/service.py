from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.booking_notes.models import BookingNote
from app.modules.booking_notes.schemas import BookingNoteCreate, BookingNoteUpdate
from app.modules.bookings.models import Booking
from app.modules.classes.models import ClassSession
from app.modules.teachers.models import Teacher
from app.shared.utils import utc_now


class BookingNoteService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_booking_note(
        self,
        booking_id: UUID,
        note_in: BookingNoteCreate,
    ) -> BookingNote:
        booking, class_session = await self._get_booking_and_class_session(booking_id)
        await self._validate_teacher_ownership(note_in.teacher_id, class_session)
        if class_session.starts_at > utc_now():
            raise BadRequestError("Booking notes can only be created after class start")

        booking_note = BookingNote(
            booking_id=booking.id,
            class_session_id=class_session.id,
            student_id=booking.student_id,
            teacher_id=note_in.teacher_id,
            note=note_in.note,
            visibility=note_in.visibility,
        )
        self.session.add(booking_note)
        await self.session.commit()
        await self.session.refresh(booking_note)
        return booking_note

    async def list_teacher_booking_notes(
        self,
        booking_id: UUID,
        teacher_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        _, class_session = await self._get_booking_and_class_session(booking_id)
        await self._validate_teacher_ownership(teacher_id, class_session)
        return await self._list_booking_notes(booking_id, pagination)

    async def list_admin_booking_notes(
        self,
        booking_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        await self._get_booking_and_class_session(booking_id)
        return await self._list_booking_notes(booking_id, pagination)

    async def update_booking_note(
        self,
        note_id: UUID,
        teacher_id: UUID,
        note_in: BookingNoteUpdate,
    ) -> BookingNote:
        booking_note = await self._get_booking_note(note_id)
        if booking_note.teacher_id != teacher_id:
            raise BadRequestError("Teacher does not own this booking note")

        _, class_session = await self._get_booking_and_class_session(
            booking_note.booking_id
        )
        await self._validate_teacher_ownership(teacher_id, class_session)

        update_data = note_in.model_dump(exclude_unset=True)
        for field in ("note", "visibility"):
            if field in update_data and update_data[field] is None:
                raise BadRequestError(f"{field} cannot be null")
        for field, value in update_data.items():
            setattr(booking_note, field, value)

        await self.session.commit()
        await self.session.refresh(booking_note)
        return booking_note

    async def _list_booking_notes(
        self,
        booking_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        statement = (
            select(BookingNote)
            .where(BookingNote.booking_id == booking_id)
            .order_by(BookingNote.created_at.asc(), BookingNote.id.asc())
        )
        return await paginate_scalars(self.session, statement, pagination)

    async def _get_booking_note(self, note_id: UUID) -> BookingNote:
        booking_note = await self.session.get(BookingNote, note_id)
        if booking_note is None:
            raise NotFoundError("Booking note not found")
        return booking_note

    async def _get_booking_and_class_session(
        self,
        booking_id: UUID,
    ) -> tuple[Booking, ClassSession]:
        booking = await self.session.get(Booking, booking_id)
        if booking is None:
            raise NotFoundError("Booking not found")
        class_session = await self.session.get(ClassSession, booking.class_session_id)
        if class_session is None:
            raise NotFoundError("Class session not found")
        return booking, class_session

    async def _validate_teacher_ownership(
        self,
        teacher_id: UUID,
        class_session: ClassSession,
    ) -> None:
        teacher = await self.session.get(Teacher, teacher_id)
        if teacher is None:
            raise NotFoundError("Teacher not found")
        if class_session.teacher_id != teacher.id:
            raise BadRequestError("Teacher is not assigned to this class session")
