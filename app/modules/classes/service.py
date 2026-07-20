from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.classes.models import ClassSession
from app.modules.classes.schemas import BatchClassSessionCreate
from app.modules.teachers.models import Teacher
from app.shared.enums import StudentProgramType


class ClassSessionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_class_sessions(
        self,
        program_type: StudentProgramType | None = None,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
    ) -> list[ClassSession]:
        statement = select(ClassSession).order_by(ClassSession.starts_at.asc())
        if program_type is not None:
            statement = statement.where(ClassSession.program_type == program_type)
        if starts_from is not None:
            statement = statement.where(ClassSession.starts_at >= starts_from)
        if starts_to is not None:
            statement = statement.where(ClassSession.starts_at <= starts_to)

        result = await self.session.scalars(statement)
        return list(result)

    async def get_class_session(self, class_session_id: UUID) -> ClassSession:
        class_session = await self.session.get(ClassSession, class_session_id)
        if class_session is None:
            raise NotFoundError("Class session not found")
        return class_session

    async def create_batch_class_session(
        self,
        class_session_in: BatchClassSessionCreate,
    ) -> ClassSession:
        if class_session_in.teacher_id is not None:
            teacher = await self.session.get(Teacher, class_session_in.teacher_id)
            if teacher is None:
                raise NotFoundError("Teacher not found")

        class_session = ClassSession(
            teacher_id=class_session_in.teacher_id,
            teacher_availability_slot_id=None,
            program_type=StudentProgramType.BATCH,
            batch_slot=class_session_in.batch_slot,
            starts_at=class_session_in.starts_at,
            ends_at=class_session_in.ends_at,
            status=class_session_in.status,
            capacity=class_session_in.capacity,
        )
        self.session.add(class_session)
        await self.session.commit()
        await self.session.refresh(class_session)
        return class_session
