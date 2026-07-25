from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError
from app.modules.batch_schedule_days.schemas import (
    BatchDayActionRequest,
    BatchDayBulkCancelRequest,
    BatchDayBulkCreate,
    BatchDayOptionCreate,
)
from app.modules.batch_schedule_days.service import BatchScheduleDayService
from app.shared.enums import BatchScheduleDayStatus, DayOfWeek


def test_batch_day_rejects_overlapping_request_options() -> None:
    service = BatchScheduleDayService(session=None)
    options = [
        BatchDayOptionCreate(
            display_label="Morning",
            starts_at=datetime(2026, 8, 3, 8, tzinfo=UTC),
            ends_at=datetime(2026, 8, 3, 10, tzinfo=UTC),
        ),
        BatchDayOptionCreate(
            display_label="Custom",
            starts_at=datetime(2026, 8, 3, 9, tzinfo=UTC),
            ends_at=datetime(2026, 8, 3, 11, tzinfo=UTC),
        ),
    ]

    with pytest.raises(ConflictError, match="Morning and Custom overlap"):
        service._ensure_no_request_overlaps(options)


@pytest.mark.asyncio
async def test_bulk_batch_day_failure_does_not_commit_partial_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = type(
        "Session",
        (),
        {"commit": AsyncMock()},
    )()
    service = BatchScheduleDayService(session)
    first_day = object()
    calls = 0

    async def fake_create_day(day_in):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConflictError("teacher overlap")
        return first_day

    monkeypatch.setattr(service, "_create_day", fake_create_day)
    bulk = BatchDayBulkCreate(
        batch_group_id=uuid4(),
        starts_from=date(2026, 8, 3),
        starts_to=date(2026, 8, 5),
        weekdays=[DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY],
        options=[
            {
                "display_label": "Morning",
                "start_time_utc": time(8),
                "end_time_utc": time(9),
            }
        ],
    )

    with pytest.raises(ConflictError, match="2026-08-05.*teacher overlap"):
        await service.create_days_bulk(bulk)

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_already_cancelled_day_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(commit=AsyncMock())
    service = BatchScheduleDayService(session)
    day_id = uuid4()
    day = SimpleNamespace(id=day_id, status=BatchScheduleDayStatus.CANCELLED)
    expected = object()
    monkeypatch.setattr(service, "_get_optional_user", AsyncMock())
    monkeypatch.setattr(service, "_lock_days", AsyncMock(return_value=[day]))
    monkeypatch.setattr(service, "_validate_days_can_be_cancelled", AsyncMock())
    cancel_locked = AsyncMock()
    monkeypatch.setattr(service, "_cancel_locked_day", cancel_locked)
    monkeypatch.setattr(service, "get_day", AsyncMock(return_value=expected))

    result = await service.cancel_day(day_id, BatchDayActionRequest(reason="duplicate"))

    assert result is expected
    cancel_locked.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_cancel_validates_all_days_before_mutating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(commit=AsyncMock())
    service = BatchScheduleDayService(session)
    days = [
        SimpleNamespace(id=uuid4(), status=BatchScheduleDayStatus.SCHEDULED),
        SimpleNamespace(id=uuid4(), status=BatchScheduleDayStatus.SCHEDULED),
    ]
    monkeypatch.setattr(service, "_get_optional_user", AsyncMock())
    monkeypatch.setattr(service, "_lock_days", AsyncMock(return_value=days))
    monkeypatch.setattr(
        service,
        "_validate_days_can_be_cancelled",
        AsyncMock(side_effect=ConflictError("Past batch schedule day")),
    )
    cancel_locked = AsyncMock()
    monkeypatch.setattr(service, "_cancel_locked_day", cancel_locked)

    with pytest.raises(ConflictError, match="Past batch schedule day"):
        await service.cancel_days_bulk(
            BatchDayBulkCancelRequest(day_ids=[day.id for day in days])
        )

    cancel_locked.assert_not_awaited()
    session.commit.assert_not_awaited()
