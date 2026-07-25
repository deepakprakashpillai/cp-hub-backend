from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.pagination import Page, PaginationParams
from app.modules.classes.service import ClassSessionService
from app.shared.enums import ClassSessionStatus, StudentProgramType


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("descending", "expected_order"),
    [
        (False, "class_sessions.starts_at ASC"),
        (True, "class_sessions.starts_at DESC"),
    ],
)
async def test_class_session_listing_filters_and_sorts_before_pagination(
    monkeypatch: pytest.MonkeyPatch,
    descending: bool,
    expected_order: str,
) -> None:
    session = object()
    pagination = PaginationParams(page=2, page_size=10)
    teacher_id = uuid4()
    batch_group_id = uuid4()
    starts_from = datetime(2026, 7, 1, tzinfo=UTC)
    starts_to = datetime(2026, 7, 31, tzinfo=UTC)
    captured = {}

    async def fake_paginate_scalars(received_session, statement, received_pagination):
        captured["sql"] = str(statement.compile(dialect=postgresql.dialect()))
        assert received_session is session
        assert received_pagination is pagination
        return Page(items=[], total=0, page=2, page_size=10)

    monkeypatch.setattr(
        "app.modules.classes.service.paginate_scalars",
        fake_paginate_scalars,
    )

    await ClassSessionService(session).list_class_sessions(
        pagination,
        program_type=StudentProgramType.BATCH,
        starts_from=starts_from,
        starts_to=starts_to,
        status=ClassSessionStatus.COMPLETED,
        teacher_id=teacher_id,
        batch_group_id=batch_group_id,
        descending=descending,
    )

    sql = captured["sql"]
    assert expected_order in sql
    assert "class_sessions.id ASC" in sql
    assert "class_sessions.program_type =" in sql
    assert "class_sessions.starts_at >=" in sql
    assert "class_sessions.starts_at <=" in sql
    assert "class_sessions.status =" in sql
    assert "class_sessions.teacher_id =" in sql
    assert "class_sessions.batch_group_id =" in sql
