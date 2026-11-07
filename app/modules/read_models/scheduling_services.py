from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PaginationParams
from app.modules.batch_groups.schemas import (
    BatchSessionBulkGenerate,
)
from app.modules.batch_groups.service import (
    BatchSessionGenerationService,
)
from app.modules.classes.models import ClassSession
from app.modules.read_models.admin_schemas import (
    AdminStudentAccessState,
)
from app.modules.schedules.models import TeacherAvailabilityRule, TeacherAvailabilitySlot
from app.modules.schedules.schemas import (
    TeacherAvailabilityBlockCreate,
    TeacherAvailabilityRuleCreate,
    TeacherAvailabilityRuleUpdate,
    TeacherAvailabilitySlotBulkCreate,
    TeacherAvailabilitySlotCreate,
    TeacherAvailabilitySlotUpdate,
)
from app.modules.schedules.service import ScheduleService
from app.modules.students.models import Student
from app.modules.users.models import User
from app.modules.users.schemas import UserUpdate
from app.modules.users.service import UserService
from app.shared.enums import (
    AvailabilitySlotSource,
    AvailabilitySlotStatus,
    SortOrder,
)


class _ServiceBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class AdminSchedulingService(_ServiceBase):
    async def update_user(self, user_id: UUID, user_in: UserUpdate) -> User:
        return await UserService(self.session).update_user(user_id, user_in)

    async def list_teacher_availability_rules(
        self,
        pagination: PaginationParams,
        teacher_id: UUID | None = None,
    ) -> Page:
        return await ScheduleService(self.session).list_teacher_availability_rules(
            pagination,
            teacher_id=teacher_id,
        )

    async def create_teacher_availability_rule(
        self,
        rule_in: TeacherAvailabilityRuleCreate,
    ) -> TeacherAvailabilityRule:
        return await ScheduleService(self.session).create_teacher_availability_rule(rule_in)

    async def get_teacher_availability_rule(self, rule_id: UUID) -> TeacherAvailabilityRule:
        return await ScheduleService(self.session).get_teacher_availability_rule(rule_id)

    async def update_teacher_availability_rule(
        self,
        rule_id: UUID,
        rule_in: TeacherAvailabilityRuleUpdate,
    ) -> TeacherAvailabilityRule:
        return await ScheduleService(self.session).update_teacher_availability_rule(
            rule_id,
            rule_in,
        )

    async def delete_teacher_availability_rule(self, rule_id: UUID) -> None:
        await ScheduleService(self.session).delete_teacher_availability_rule(rule_id)

    async def list_teacher_availability_slots(
        self,
        pagination: PaginationParams,
        teacher_id: UUID | None = None,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
        status: AvailabilitySlotStatus | None = None,
        source: AvailabilitySlotSource | None = None,
        sort_order: SortOrder = SortOrder.ASC,
    ) -> Page:
        return await ScheduleService(self.session).list_teacher_availability_slots(
            pagination,
            teacher_id=teacher_id,
            starts_from=starts_from,
            starts_to=starts_to,
            status=status,
            source=source,
            descending=sort_order == SortOrder.DESC,
        )

    async def create_teacher_availability_slot(
        self,
        slot_in: TeacherAvailabilitySlotCreate,
    ) -> TeacherAvailabilitySlot:
        return await ScheduleService(self.session).create_teacher_availability_slot(slot_in)

    async def create_teacher_availability_slots_bulk(
        self,
        slots_in: TeacherAvailabilitySlotBulkCreate,
    ) -> list[TeacherAvailabilitySlot]:
        return await ScheduleService(self.session).create_teacher_availability_slots_bulk(slots_in)

    async def create_teacher_availability_block(
        self,
        block_in: TeacherAvailabilityBlockCreate,
    ) -> TeacherAvailabilitySlot:
        return await ScheduleService(self.session).create_teacher_availability_block(block_in)

    async def get_teacher_availability_slot(self, slot_id: UUID) -> TeacherAvailabilitySlot:
        return await ScheduleService(self.session).get_teacher_availability_slot(slot_id)

    async def update_teacher_availability_slot(
        self,
        slot_id: UUID,
        slot_in: TeacherAvailabilitySlotUpdate,
    ) -> TeacherAvailabilitySlot:
        return await ScheduleService(self.session).update_teacher_availability_slot(
            slot_id,
            slot_in,
        )

    async def delete_teacher_availability_slot(self, slot_id: UUID) -> None:
        await ScheduleService(self.session).delete_teacher_availability_slot(slot_id)

    async def generate_teacher_availability_slots(
        self,
        teacher_id: UUID,
        days_ahead: int = 14,
    ):
        return await ScheduleService(self.session).generate_teacher_availability_slots(
            teacher_id,
            days_ahead=days_ahead,
        )

    async def generate_batch_sessions(
        self,
        batch_group_id: UUID,
        generation_in: BatchSessionBulkGenerate,
    ) -> list[ClassSession]:
        return await BatchSessionGenerationService(self.session).generate_batch_sessions(
            batch_group_id,
            generation_in,
        )


def _resolve_dashboard_window(
    *,
    starts_from: datetime | None,
    starts_to: datetime | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    if starts_from is None:
        starts_from = datetime.combine(now.date(), time.min, tzinfo=UTC)
    if starts_to is None:
        starts_to = starts_from + timedelta(days=1)
    if starts_from >= starts_to:
        raise ValueError("starts_from must be before starts_to")
    return starts_from, starts_to


def _normalize_search_query(q: str | None) -> str | None:
    if q is None:
        return None
    normalized = q.strip()
    return normalized or None


def _model_values(model) -> dict:
    return {key: value for key, value in vars(model).items() if not key.startswith("_")}


def _student_access_state_clause(access_state: AdminStudentAccessState, now: datetime):
    if access_state == AdminStudentAccessState.VALID:
        return (
            Student.access_starts_at.is_not(None)
            & (Student.access_starts_at <= now)
            & Student.access_ends_at.is_not(None)
            & (Student.access_ends_at > now)
        )
    if access_state == AdminStudentAccessState.EXPIRED:
        return Student.access_ends_at.is_not(None) & (Student.access_ends_at <= now)
    if access_state == AdminStudentAccessState.NOT_STARTED:
        return Student.access_starts_at.is_not(None) & (Student.access_starts_at > now)
    return or_(Student.access_starts_at.is_(None), Student.access_ends_at.is_(None))
