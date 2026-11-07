from datetime import UTC, date, datetime, time
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.batch_schedule_days.schemas import (
    BatchDayBulkCreate,
    BatchDayCreate,
    BatchScheduleDefaultsUpdate,
)
from app.shared.enums import DayOfWeek


def _option(label: str, hour: int) -> dict:
    return {
        "display_label": label,
        "starts_at": datetime(2026, 8, 2, hour, tzinfo=UTC),
        "ends_at": datetime(2026, 8, 2, hour + 1, tzinfo=UTC),
    }


@pytest.mark.parametrize("option_count", [2, 3, 4])
def test_batch_day_accepts_configurable_option_counts(option_count: int) -> None:
    day = BatchDayCreate(
        batch_group_id=uuid4(),
        schedule_date=date(2026, 8, 2),
        options=[_option(f"Option {index}", 6 + (index * 2)) for index in range(option_count)],
    )

    assert len(day.options) == option_count


def test_batch_day_allows_defaults_when_options_are_omitted() -> None:
    day = BatchDayCreate(
        batch_group_id=uuid4(),
        schedule_date=date(2026, 8, 2),
    )

    assert day.options is None


def test_batch_day_rejects_option_on_another_utc_date() -> None:
    with pytest.raises(ValidationError, match="schedule_date in UTC"):
        BatchDayCreate(
            batch_group_id=uuid4(),
            schedule_date=date(2026, 8, 2),
            options=[
                {
                    "display_label": "Evening",
                    "starts_at": datetime(2026, 8, 3, 18, tzinfo=UTC),
                    "ends_at": datetime(2026, 8, 3, 19, tzinfo=UTC),
                }
            ],
        )


def test_batch_day_rejects_naive_option_time() -> None:
    with pytest.raises(ValidationError, match="timezone info"):
        BatchDayCreate(
            batch_group_id=uuid4(),
            schedule_date=date(2026, 8, 2),
            options=[
                {
                    "display_label": "Morning",
                    "starts_at": datetime(2026, 8, 2, 8),
                    "ends_at": datetime(2026, 8, 2, 9),
                }
            ],
        )


def test_defaults_timezone_is_read_only() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BatchScheduleDefaultsUpdate(timezone="Asia/Kolkata")


def test_bulk_schedule_accepts_four_custom_options() -> None:
    bulk = BatchDayBulkCreate(
        batch_group_id=uuid4(),
        starts_from=date(2026, 8, 3),
        starts_to=date(2026, 8, 9),
        weekdays=[DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY, DayOfWeek.FRIDAY],
        options=[
            {
                "display_label": label,
                "start_time_utc": time(hour),
                "end_time_utc": time(hour + 1),
            }
            for label, hour in [
                ("Early", 6),
                ("Morning", 9),
                ("Noon", 12),
                ("Evening", 18),
            ]
        ],
    )

    assert len(bulk.options) == 4
