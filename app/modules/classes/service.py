from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.batch_groups.models import BatchGroup
from app.modules.classes.models import ClassSession
from app.modules.classes.schemas import BatchClassSessionCreate
from app.modules.teachers.models import Teacher
from app.shared.enums import ClassSessionStatus, StudentProgramType


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
        batch_group = await self.session.get(BatchGroup, class_session_in.batch_group_id)
        if batch_group is None:
            raise NotFoundError("Batch group not found")
        if not batch_group.is_active:
            raise ConflictError("Cannot create sessions for an inactive batch group")

        if class_session_in.teacher_id is not None:
            teacher = await self.session.get(Teacher, class_session_in.teacher_id)
            if teacher is None:
                raise NotFoundError("Teacher not found")

        await self._ensure_no_batch_session_overlap(
            batch_group_id=batch_group.id,
            starts_at=class_session_in.starts_at,
            ends_at=class_session_in.ends_at,
        )

        class_session = ClassSession(
            teacher_id=class_session_in.teacher_id,
            teacher_availability_slot_id=None,
            batch_group_id=batch_group.id,
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

    async def _ensure_no_batch_session_overlap(
        self,
        *,
        batch_group_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> None:
        overlapping_session = await self.session.scalar(
            select(ClassSession).where(
                ClassSession.batch_group_id == batch_group_id,
                ClassSession.status != ClassSessionStatus.CANCELLED,
                ClassSession.starts_at < ends_at,
                ClassSession.ends_at > starts_at,
            )
        )
        if overlapping_session is not None:
            raise ConflictError("Batch group already has an overlapping class session")
