from datetime import UTC, datetime, time
from uuid import uuid4

from app.modules.schedules.models import TeacherAvailabilityRule
from app.modules.schedules.slot_generation import build_expected_rule_slots
from app.shared.enums import DayOfWeek


def test_build_expected_rule_slots_skips_past_slots_today() -> None:
    rule = TeacherAvailabilityRule(
        teacher_id=uuid4(),
        day_of_week=DayOfWeek.MONDAY,
        start_time_utc=time(9, 0),
        end_time_utc=time(12, 0),
        slot_duration_minutes=60,
        is_active=True,
    )

    slots = build_expected_rule_slots(
        rule,
        now=datetime(2026, 7, 20, 9, 15, tzinfo=UTC),
        days_ahead=0,
    )

    assert slots == [
        (
            datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
            datetime(2026, 7, 20, 11, 0, tzinfo=UTC),
        ),
        (
            datetime(2026, 7, 20, 11, 0, tzinfo=UTC),
            datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
        ),
    ]


def test_build_expected_rule_slots_includes_date_fourteen_days_ahead() -> None:
    rule = TeacherAvailabilityRule(
        teacher_id=uuid4(),
        day_of_week=DayOfWeek.MONDAY,
        start_time_utc=time(3, 30),
        end_time_utc=time(4, 30),
        slot_duration_minutes=60,
        is_active=True,
    )

    slots = build_expected_rule_slots(
        rule,
        now=datetime(2026, 7, 20, 1, 0, tzinfo=UTC),
        days_ahead=14,
    )

    assert slots == [
        (
            datetime(2026, 7, 20, 3, 30, tzinfo=UTC),
            datetime(2026, 7, 20, 4, 30, tzinfo=UTC),
        ),
        (
            datetime(2026, 7, 27, 3, 30, tzinfo=UTC),
            datetime(2026, 7, 27, 4, 30, tzinfo=UTC),
        ),
        (
            datetime(2026, 8, 3, 3, 30, tzinfo=UTC),
            datetime(2026, 8, 3, 4, 30, tzinfo=UTC),
        ),
    ]
