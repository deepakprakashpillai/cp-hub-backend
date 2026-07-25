from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.pagination import Page, PaginationParams
from app.modules.schedules.service import ScheduleService
from app.shared.enums import AvailabilitySlotSource, AvailabilitySlotStatus


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "source", "descending", "expected_order"),
    [
        (
            AvailabilitySlotStatus.AVAILABLE,
            None,
            False,
            "teacher_availability_slots.starts_at ASC",
        ),
        (
            None,
            AvailabilitySlotSource.MANUAL,
            False,
            "teacher_availability_slots.starts_at ASC",
        ),
        (
            AvailabilitySlotStatus.BLOCKED,
            AvailabilitySlotSource.MANUAL,
            True,
            "teacher_availability_slots.starts_at DESC",
        ),
    ],
)
async def test_slot_listing_composes_filters_sorting_and_pagination(
    monkeypatch: pytest.MonkeyPatch,
    status: AvailabilitySlotStatus | None,
    source: AvailabilitySlotSource | None,
    descending: bool,
    expected_order: str,
) -> None:
    session = object()
    pagination = PaginationParams(page=3, page_size=10)
    teacher_id = uuid4()
    starts_from = datetime(2026, 7, 1, tzinfo=UTC)
    starts_to = datetime(2026, 7, 31, tzinfo=UTC)
    captured = {}

    async def fake_paginate_scalars(received_session, statement, received_pagination):
        captured["sql"] = str(statement.compile(dialect=postgresql.dialect()))
        assert received_session is session
        assert received_pagination is pagination
        return Page(items=[], total=0, page=3, page_size=10)

    monkeypatch.setattr(
        "app.modules.schedules.service.paginate_scalars",
        fake_paginate_scalars,
    )

    await ScheduleService(session).list_teacher_availability_slots(
        pagination,
        teacher_id=teacher_id,
        starts_from=starts_from,
        starts_to=starts_to,
        status=status,
        source=source,
        descending=descending,
    )

    sql = captured["sql"]
    assert expected_order in sql
    assert "teacher_availability_slots.id ASC" in sql
    assert "teacher_availability_slots.teacher_id =" in sql
    assert "teacher_availability_slots.starts_at >=" in sql
    assert "teacher_availability_slots.starts_at <=" in sql
    assert ("teacher_availability_slots.status =" in sql) is (status is not None)
    assert ("teacher_availability_slots.source =" in sql) is (source is not None)
