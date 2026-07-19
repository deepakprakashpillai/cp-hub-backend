from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.schedules.models import TeacherAvailabilityRule, TeacherAvailabilitySlot
from app.modules.schedules.schemas import (
    TeacherAvailabilityBlockCreate,
    TeacherAvailabilityRuleCreate,
    TeacherAvailabilityRuleUpdate,
    TeacherAvailabilitySlotBulkCreate,
    TeacherAvailabilitySlotCreate,
    TeacherAvailabilitySlotUpdate,
)
from app.modules.schedules.slot_generation import sync_teacher_availability_slots
from app.modules.teachers.models import Teacher
from app.shared.enums import AvailabilitySlotSource, AvailabilitySlotStatus
from app.shared.utils import utc_now


class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_teacher_availability_rules(
        self,
        teacher_id: UUID | None = None,
    ) -> list[TeacherAvailabilityRule]:
        statement = select(TeacherAvailabilityRule).order_by(
            TeacherAvailabilityRule.created_at.desc()
        )
        if teacher_id is not None:
            statement = statement.where(TeacherAvailabilityRule.teacher_id == teacher_id)

        result = await self.session.scalars(statement)
        return list(result)

    async def get_teacher_availability_rule(self, rule_id: UUID) -> TeacherAvailabilityRule:
        rule = await self.session.get(TeacherAvailabilityRule, rule_id)
        if rule is None:
            raise NotFoundError("Teacher availability rule not found")
        return rule

    async def create_teacher_availability_rule(
        self,
        rule_in: TeacherAvailabilityRuleCreate,
    ) -> TeacherAvailabilityRule:
        await self._get_teacher(rule_in.teacher_id)

        rule = TeacherAvailabilityRule(**rule_in.model_dump())
        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        await sync_teacher_availability_slots(self.session, rule_id=rule.id)
        await self.session.refresh(rule)
        return rule

    async def update_teacher_availability_rule(
        self,
        rule_id: UUID,
        rule_in: TeacherAvailabilityRuleUpdate,
    ) -> TeacherAvailabilityRule:
        rule = await self.get_teacher_availability_rule(rule_id)
        update_data = rule_in.model_dump(exclude_unset=True)

        if not update_data:
            return rule

        for field, value in update_data.items():
            setattr(rule, field, value)

        if rule.start_time_utc >= rule.end_time_utc:
            raise ConflictError("start_time_utc must be before end_time_utc")

        await self.session.commit()
        await self.session.refresh(rule)
        await sync_teacher_availability_slots(self.session, rule_id=rule.id)
        await self.session.refresh(rule)
        return rule

    async def delete_teacher_availability_rule(self, rule_id: UUID) -> None:
        rule = await self.get_teacher_availability_rule(rule_id)
        rule.is_active = False
        await self.session.commit()
        await sync_teacher_availability_slots(self.session, rule_id=rule.id)

    async def list_teacher_availability_slots(
        self,
        teacher_id: UUID | None = None,
        starts_from=None,
        starts_to=None,
    ) -> list[TeacherAvailabilitySlot]:
        statement = select(TeacherAvailabilitySlot).order_by(
            TeacherAvailabilitySlot.starts_at.asc()
        )
        if teacher_id is not None:
            statement = statement.where(TeacherAvailabilitySlot.teacher_id == teacher_id)
        if starts_from is not None:
            statement = statement.where(TeacherAvailabilitySlot.starts_at >= starts_from)
        if starts_to is not None:
            statement = statement.where(TeacherAvailabilitySlot.starts_at <= starts_to)

        result = await self.session.scalars(statement)
        return list(result)

    async def get_teacher_availability_slot(self, slot_id: UUID) -> TeacherAvailabilitySlot:
        slot = await self.session.get(TeacherAvailabilitySlot, slot_id)
        if slot is None:
            raise NotFoundError("Teacher availability slot not found")
        return slot

    async def create_teacher_availability_slot(
        self,
        slot_in: TeacherAvailabilitySlotCreate,
    ) -> TeacherAvailabilitySlot:
        await self._validate_slot_create(slot_in)
        await self._ensure_no_slot_overlap(
            teacher_id=slot_in.teacher_id,
            starts_at=slot_in.starts_at,
            ends_at=slot_in.ends_at,
            status=slot_in.status,
        )
        slot = TeacherAvailabilitySlot(**slot_in.model_dump())
        self.session.add(slot)
        await self.session.commit()
        await self.session.refresh(slot)
        return slot

    async def create_teacher_availability_slots_bulk(
        self,
        slots_in: TeacherAvailabilitySlotBulkCreate,
    ) -> list[TeacherAvailabilitySlot]:
        for slot_in in slots_in.slots:
            await self._validate_slot_create(slot_in)
            if slot_in.source != AvailabilitySlotSource.MANUAL or slot_in.rule_id is not None:
                raise ConflictError("Bulk slot creation only supports manual slots")

        self._ensure_no_overlaps_within_batch(slots_in.slots)

        slots: list[TeacherAvailabilitySlot] = []
        for slot_in in slots_in.slots:
            await self._ensure_no_slot_overlap(
                teacher_id=slot_in.teacher_id,
                starts_at=slot_in.starts_at,
                ends_at=slot_in.ends_at,
                status=slot_in.status,
            )
            slot = TeacherAvailabilitySlot(**slot_in.model_dump())
            self.session.add(slot)
            slots.append(slot)

        await self.session.commit()
        for slot in slots:
            await self.session.refresh(slot)
        return slots

    async def create_teacher_availability_block(
        self,
        block_in: TeacherAvailabilityBlockCreate,
    ) -> TeacherAvailabilitySlot:
        slot_in = TeacherAvailabilitySlotCreate(
            teacher_id=block_in.teacher_id,
            rule_id=None,
            source=AvailabilitySlotSource.MANUAL,
            starts_at=block_in.starts_at,
            ends_at=block_in.ends_at,
            status=AvailabilitySlotStatus.BLOCKED,
        )
        return await self.create_teacher_availability_slot(slot_in)

    async def update_teacher_availability_slot(
        self,
        slot_id: UUID,
        slot_in: TeacherAvailabilitySlotUpdate,
    ) -> TeacherAvailabilitySlot:
        slot = await self.get_teacher_availability_slot(slot_id)

        if slot.status == AvailabilitySlotStatus.BOOKED:
            raise ConflictError("Booked slots cannot be edited")

        update_data = slot_in.model_dump(exclude_unset=True)
        if not update_data:
            return slot

        starts_at = update_data.get("starts_at", slot.starts_at)
        ends_at = update_data.get("ends_at", slot.ends_at)
        status = update_data.get("status", slot.status)

        if starts_at >= ends_at:
            raise ConflictError("starts_at must be before ends_at")

        await self._ensure_no_slot_overlap(
            teacher_id=slot.teacher_id,
            starts_at=starts_at,
            ends_at=ends_at,
            status=status,
            exclude_slot_id=slot.id,
        )

        for field, value in update_data.items():
            setattr(slot, field, value)

        await self.session.commit()
        await self.session.refresh(slot)
        return slot

    async def delete_teacher_availability_slot(self, slot_id: UUID) -> None:
        slot = await self.get_teacher_availability_slot(slot_id)

        if slot.status == AvailabilitySlotStatus.BOOKED:
            raise ConflictError("Booked slots cannot be deleted")

        slot.status = AvailabilitySlotStatus.CANCELLED
        await self.session.commit()

    async def _get_teacher(self, teacher_id: UUID) -> Teacher:
        teacher = await self.session.get(Teacher, teacher_id)
        if teacher is None:
            raise NotFoundError("Teacher not found")
        return teacher

    async def _validate_slot_create(self, slot_in: TeacherAvailabilitySlotCreate) -> None:
        await self._get_teacher(slot_in.teacher_id)

        if slot_in.source == AvailabilitySlotSource.RULE:
            if slot_in.rule_id is None:
                raise ConflictError("Rule generated slots must include rule_id")
            rule = await self.get_teacher_availability_rule(slot_in.rule_id)
            if rule.teacher_id != slot_in.teacher_id:
                raise ConflictError("Rule does not belong to this teacher")

        if slot_in.source == AvailabilitySlotSource.MANUAL and slot_in.rule_id is not None:
            raise ConflictError("Manual slots cannot include rule_id")

    async def _ensure_no_slot_overlap(
        self,
        teacher_id: UUID,
        starts_at,
        ends_at,
        status: AvailabilitySlotStatus,
        exclude_slot_id: UUID | None = None,
    ) -> None:
        if status == AvailabilitySlotStatus.CANCELLED:
            return

        statement = select(TeacherAvailabilitySlot).where(
            TeacherAvailabilitySlot.teacher_id == teacher_id,
            TeacherAvailabilitySlot.status != AvailabilitySlotStatus.CANCELLED,
            TeacherAvailabilitySlot.starts_at < ends_at,
            TeacherAvailabilitySlot.ends_at > starts_at,
        )
        if exclude_slot_id is not None:
            statement = statement.where(TeacherAvailabilitySlot.id != exclude_slot_id)

        overlapping_slot = await self.session.scalar(statement)
        if overlapping_slot is not None:
            raise ConflictError("Teacher already has an overlapping active slot")

    def _ensure_no_overlaps_within_batch(self, slots: list[TeacherAvailabilitySlotCreate]) -> None:
        active_slots = [
            slot
            for slot in slots
            if slot.status != AvailabilitySlotStatus.CANCELLED
        ]

        for index, slot in enumerate(active_slots):
            for other_slot in active_slots[index + 1 :]:
                if slot.teacher_id != other_slot.teacher_id:
                    continue
                if slot.starts_at < other_slot.ends_at and slot.ends_at > other_slot.starts_at:
                    raise ConflictError("Bulk request contains overlapping slots")

    async def _cancel_future_available_rule_slots(self, rule_id: UUID) -> None:
        result = await self.session.scalars(
            select(TeacherAvailabilitySlot).where(
                TeacherAvailabilitySlot.rule_id == rule_id,
                TeacherAvailabilitySlot.source == AvailabilitySlotSource.RULE,
                TeacherAvailabilitySlot.status == AvailabilitySlotStatus.AVAILABLE,
                TeacherAvailabilitySlot.starts_at >= utc_now(),
            )
        )
        for slot in result:
            slot.status = AvailabilitySlotStatus.CANCELLED
