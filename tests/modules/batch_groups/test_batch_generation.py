from datetime import UTC, date, datetime, time

import pytest
from pydantic import ValidationError

from app.modules.batch_groups.schemas import BatchSessionBulkGenerate
from app.modules.batch_groups.service import build_utc_session_datetimes
from app.shared.enums import BatchSlot, DayOfWeek


def test_build_utc_session_datetimes_allows_cross_midnight_sessions() -> None:
    starts_at, ends_at = build_utc_session_datetimes(
        session_date=date(2026, 7, 22),
        start_time_utc=time(23, 30),
        end_time_utc=time(0, 30),
    )

    assert starts_at == datetime(2026, 7, 22, 23, 30, tzinfo=UTC)
    assert ends_at == datetime(2026, 7, 23, 0, 30, tzinfo=UTC)


def test_batch_generation_rejects_date_ranges_over_ninety_days() -> None:
    with pytest.raises(ValidationError, match="date range cannot exceed 90 days"):
        BatchSessionBulkGenerate(
            starts_from=date(2026, 7, 1),
            starts_to=date(2026, 9, 29),
            weekdays=[DayOfWeek.MONDAY],
            sessions=[
                {
                    "batch_slot": BatchSlot.MORNING,
                    "start_time_utc": time(8, 0),
                    "end_time_utc": time(9, 0),
                }
            ],
        )


def test_batch_generation_rejects_duplicate_weekdays() -> None:
    with pytest.raises(ValidationError, match="weekdays cannot contain duplicates"):
        BatchSessionBulkGenerate(
            starts_from=date(2026, 7, 1),
            starts_to=date(2026, 7, 10),
            weekdays=[DayOfWeek.MONDAY, DayOfWeek.MONDAY],
            sessions=[
                {
                    "batch_slot": BatchSlot.MORNING,
                    "start_time_utc": time(8, 0),
                    "end_time_utc": time(9, 0),
                }
            ],
        )


def test_batch_generation_rejects_duplicate_batch_slots() -> None:
    with pytest.raises(ValidationError, match="duplicate batch_slot"):
        BatchSessionBulkGenerate(
            starts_from=date(2026, 7, 1),
            starts_to=date(2026, 7, 10),
            weekdays=[DayOfWeek.MONDAY],
            sessions=[
                {
                    "batch_slot": BatchSlot.MORNING,
                    "start_time_utc": time(8, 0),
                    "end_time_utc": time(9, 0),
                },
                {
                    "batch_slot": BatchSlot.MORNING,
                    "start_time_utc": time(10, 0),
                    "end_time_utc": time(11, 0),
                },
            ],
        )
