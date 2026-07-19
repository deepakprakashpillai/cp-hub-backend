from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.schedules.models import TeacherAvailabilityRule, TeacherAvailabilitySlot
from app.shared.enums import AvailabilitySlotSource, AvailabilitySlotStatus, DayOfWeek
from app.shared.utils import utc_now

SLOT_GENERATION_DAYS = 14

DAY_TO_INDEX = {
    DayOfWeek.MONDAY: 0,
    DayOfWeek.TUESDAY: 1,
    DayOfWeek.WEDNESDAY: 2,
    DayOfWeek.THURSDAY: 3,
    DayOfWeek.FRIDAY: 4,
    DayOfWeek.SATURDAY: 5,
    DayOfWeek.SUNDAY: 6,
}


@dataclass(slots=True)
class SlotGenerationResult:
    rules_checked: int = 0
    slots_created: int = 0
    slots_cancelled: int = 0
    slots_skipped: int = 0

    def merge(self, other: "SlotGenerationResult") -> None:
        self.rules_checked += other.rules_checked
        self.slots_created += other.slots_created
        self.slots_cancelled += other.slots_cancelled
        self.slots_skipped += other.slots_skipped


def build_expected_rule_slots(
    rule: TeacherAvailabilityRule,
    *,
    now: datetime,
    days_ahead: int = SLOT_GENERATION_DAYS,
) -> list[tuple[datetime, datetime]]:
    now = _as_utc(now)
    window_end_date = now.date() + timedelta(days=days_ahead)
    slot_duration = timedelta(minutes=rule.slot_duration_minutes)
    expected_slots: list[tuple[datetime, datetime]] = []

    current_date = now.date()
    while current_date <= window_end_date:
        if current_date.weekday() == DAY_TO_INDEX[rule.day_of_week]:
            expected_slots.extend(
                _build_slots_for_date(
                    current_date=current_date,
                    start_time=rule.start_time_utc,
                    end_time=rule.end_time_utc,
                    slot_duration=slot_duration,
                    now=now,
                )
            )
        current_date += timedelta(days=1)

    return expected_slots


async def sync_teacher_availability_slots(
    session: AsyncSession,
    *,
    teacher_id: UUID | None = None,
    rule_id: UUID | None = None,
    now: datetime | None = None,
    days_ahead: int = SLOT_GENERATION_DAYS,
) -> SlotGenerationResult:
    generation_now = _as_utc(now or utc_now())
    rules = await _get_rules(session, teacher_id=teacher_id, rule_id=rule_id)
    result = SlotGenerationResult(rules_checked=len(rules))

    for rule in rules:
        rule_result = await _sync_rule_slots(
            session,
            rule=rule,
            now=generation_now,
            days_ahead=days_ahead,
        )
        result.merge(rule_result)

    await session.commit()
    return result


async def _get_rules(
    session: AsyncSession,
    *,
    teacher_id: UUID | None,
    rule_id: UUID | None,
) -> list[TeacherAvailabilityRule]:
    statement = select(TeacherAvailabilityRule)
    if rule_id is not None:
        statement = statement.where(TeacherAvailabilityRule.id == rule_id)
    else:
        statement = statement.where(TeacherAvailabilityRule.is_active.is_(True))
        if teacher_id is not None:
            statement = statement.where(TeacherAvailabilityRule.teacher_id == teacher_id)

    result = await session.scalars(statement)
    return list(result)


async def _sync_rule_slots(
    session: AsyncSession,
    *,
    rule: TeacherAvailabilityRule,
    now: datetime,
    days_ahead: int,
) -> SlotGenerationResult:
    expected_slots = build_expected_rule_slots(rule, now=now, days_ahead=days_ahead)
    if not rule.is_active:
        expected_slots = []

    expected_keys = set(expected_slots)
    window_end = _window_end(now, days_ahead)
    result = SlotGenerationResult()

    generated_slots = await _get_future_generated_slots(session, rule, now, window_end)
    for slot in generated_slots:
        if (
            slot.status == AvailabilitySlotStatus.AVAILABLE
            and (slot.starts_at, slot.ends_at) not in expected_keys
        ):
            slot.status = AvailabilitySlotStatus.CANCELLED
            result.slots_cancelled += 1

    await session.flush()
    active_slots = await _get_future_active_slots(session, rule.teacher_id, now, window_end)

    for starts_at, ends_at in expected_slots:
        if _has_exact_slot(active_slots, starts_at, ends_at):
            result.slots_skipped += 1
            continue
        if _has_overlapping_slot(active_slots, starts_at, ends_at):
            result.slots_skipped += 1
            continue

        slot = TeacherAvailabilitySlot(
            teacher_id=rule.teacher_id,
            rule_id=rule.id,
            source=AvailabilitySlotSource.RULE,
            starts_at=starts_at,
            ends_at=ends_at,
            status=AvailabilitySlotStatus.AVAILABLE,
        )
        session.add(slot)
        active_slots.append(slot)
        result.slots_created += 1

    return result


async def _get_future_generated_slots(
    session: AsyncSession,
    rule: TeacherAvailabilityRule,
    now: datetime,
    window_end: datetime,
) -> list[TeacherAvailabilitySlot]:
    result = await session.scalars(
        select(TeacherAvailabilitySlot).where(
            TeacherAvailabilitySlot.rule_id == rule.id,
            TeacherAvailabilitySlot.source == AvailabilitySlotSource.RULE,
            TeacherAvailabilitySlot.starts_at >= now,
            TeacherAvailabilitySlot.starts_at <= window_end,
        )
    )
    return list(result)


async def _get_future_active_slots(
    session: AsyncSession,
    teacher_id: UUID,
    now: datetime,
    window_end: datetime,
) -> list[TeacherAvailabilitySlot]:
    result = await session.scalars(
        select(TeacherAvailabilitySlot).where(
            TeacherAvailabilitySlot.teacher_id == teacher_id,
            TeacherAvailabilitySlot.status != AvailabilitySlotStatus.CANCELLED,
            TeacherAvailabilitySlot.starts_at >= now,
            TeacherAvailabilitySlot.starts_at <= window_end,
        )
    )
    return list(result)


def _build_slots_for_date(
    *,
    current_date: date,
    start_time: time,
    end_time: time,
    slot_duration: timedelta,
    now: datetime,
) -> list[tuple[datetime, datetime]]:
    slots: list[tuple[datetime, datetime]] = []
    slot_start = datetime.combine(current_date, start_time, tzinfo=UTC)
    rule_end = datetime.combine(current_date, end_time, tzinfo=UTC)

    while slot_start + slot_duration <= rule_end:
        slot_end = slot_start + slot_duration
        if slot_start > now:
            slots.append((slot_start, slot_end))
        slot_start = slot_end

    return slots


def _has_exact_slot(
    slots: list[TeacherAvailabilitySlot],
    starts_at: datetime,
    ends_at: datetime,
) -> bool:
    return any(slot.starts_at == starts_at and slot.ends_at == ends_at for slot in slots)


def _has_overlapping_slot(
    slots: list[TeacherAvailabilitySlot],
    starts_at: datetime,
    ends_at: datetime,
) -> bool:
    return any(slot.starts_at < ends_at and slot.ends_at > starts_at for slot in slots)


def _window_end(now: datetime, days_ahead: int) -> datetime:
    return datetime.combine(now.date() + timedelta(days=days_ahead), time.max, tzinfo=UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
