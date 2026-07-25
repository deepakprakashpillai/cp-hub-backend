from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.pagination import PaginationParams
from app.modules.admin.schemas import (
    AdminBatchGroupSortBy,
    AdminPackageSortBy,
    SortOrder,
)
from app.modules.admin.service import AdminService
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.classes.service import ClassSessionService
from app.modules.students.models import Student
from app.modules.users.models import User
from app.shared.enums import (
    BookingEventType,
    BookingStatus,
    ClassSessionStatus,
    StudentProgramType,
    StudentStatus,
    UserRole,
)


@pytest.mark.asyncio
async def test_admin_class_projection_search_and_filters_apply_before_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    pagination = PaginationParams(page=3, page_size=10)
    captured = {}

    async def fake_paginate_rows(received_session, statement, received_pagination):
        assert received_session is session
        assert received_pagination is pagination
        captured["sql"] = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        return [], 37

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    result = await AdminService(session).list_class_sessions(
        pagination,
        q="maya",
        program_type=StudentProgramType.BATCH,
        status=ClassSessionStatus.SCHEDULED,
        teacher_id=uuid4(),
        batch_group_id=uuid4(),
        starts_from=datetime(2026, 8, 1, tzinfo=UTC),
        starts_to=datetime(2026, 9, 1, tzinfo=UTC),
        sort_order=SortOrder.DESC,
    )

    assert result.total == 37
    sql = captured["sql"]
    assert "booking_counts" not in sql
    assert "count(*) FILTER (WHERE bookings.status = 'booked')" in sql
    assert "users_1.full_name ILIKE '%%maya%%'" in sql
    assert "batch_groups.name ILIKE '%%maya%%'" in sql
    assert "EXISTS (SELECT bookings_2.id" in sql
    assert "bookings_2.status != 'cancelled'" in sql
    assert "class_sessions.starts_at DESC, class_sessions.id ASC" in sql


@pytest.mark.asyncio
async def test_admin_batch_group_projection_filters_and_sorts_aggregate_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    pagination = PaginationParams(page=1, page_size=25)
    captured = {}

    async def fake_paginate_rows(received_session, statement, received_pagination):
        captured["sql"] = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        return [], 2

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    result = await AdminService(session).list_batch_groups(
        pagination,
        q="evening",
        is_active=True,
        sort_by=AdminBatchGroupSortBy.ACTIVE_MEMBER_COUNT,
        sort_order=SortOrder.DESC,
    )

    assert result.total == 2
    sql = captured["sql"]
    assert "student_batch_memberships.is_active IS true" in sql
    assert "class_sessions.status = 'scheduled'" in sql
    assert "batch_groups.name ILIKE '%%evening%%'" in sql
    assert "batch_groups.is_active IS true" in sql
    assert "coalesce(anon_1.active_member_count, 0) DESC, batch_groups.id ASC" in sql


@pytest.mark.asyncio
async def test_admin_package_search_filter_and_sort_apply_before_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    pagination = PaginationParams(page=2, page_size=5)
    captured = {}

    async def fake_paginate_rows(received_session, statement, received_pagination):
        captured["sql"] = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        return [], 7

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    result = await AdminService(session).list_packages(
        pagination,
        q="quarter",
        is_active=False,
        sort_by=AdminPackageSortBy.PRICE_AMOUNT,
        sort_order=SortOrder.ASC,
    )

    assert result.total == 7
    sql = captured["sql"]
    assert "packages.name ILIKE '%%quarter%%'" in sql
    assert "packages.is_active IS false" in sql
    assert "packages.price_amount ASC, packages.id ASC" in sql


@pytest.mark.asyncio
async def test_admin_class_activity_aggregates_actor_and_system_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    pagination = PaginationParams(page=2, page_size=10)
    class_session_id = uuid4()
    student_user = User(
        id=uuid4(),
        full_name="Maya Rao",
        email="maya@example.com",
        role=UserRole.STUDENT,
        is_active=True,
    )
    actor_user = User(
        id=uuid4(),
        full_name="Admin User",
        email="admin@example.com",
        role=UserRole.ADMIN,
        is_active=True,
    )
    student = Student(
        id=uuid4(),
        user_id=student_user.id,
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ACTIVE,
    )
    booking = Booking(
        id=uuid4(),
        student_id=student.id,
        class_session_id=class_session_id,
        status=BookingStatus.BOOKED,
        booked_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    actor_event = BookingEvent(
        id=uuid4(),
        booking_id=booking.id,
        event_type=BookingEventType.ATTENDANCE_MARKED,
        actor_user_id=actor_user.id,
        reason="present",
        event_metadata={"old_status": "booked", "new_status": "attended"},
        created_at=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
    )
    system_event = BookingEvent(
        id=uuid4(),
        booking_id=booking.id,
        event_type=BookingEventType.BOOKED,
        actor_user_id=None,
        reason="booked",
        event_metadata={},
        created_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
    )
    captured = {}

    async def fake_get_class_session(self, received_class_session_id):
        assert received_class_session_id == class_session_id
        return object()

    async def fake_paginate_rows(received_session, statement, received_pagination):
        assert received_session is session
        assert received_pagination is pagination
        captured["sql"] = str(statement.compile(dialect=postgresql.dialect()))
        return [
            (actor_event, booking, student, student_user, actor_user),
            (system_event, booking, student, student_user, None),
        ], 12

    monkeypatch.setattr(
        ClassSessionService,
        "get_class_session",
        fake_get_class_session,
    )
    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    result = await AdminService(session).list_class_activity(
        class_session_id,
        pagination,
    )

    assert result.total == 12
    assert result.page == 2
    assert result.items[0].student.full_name == "Maya Rao"
    assert result.items[0].actor.full_name == "Admin User"
    assert result.items[0].actor.role == UserRole.ADMIN
    assert result.items[0].actor_label == "Admin User"
    assert result.items[0].metadata["new_status"] == "attended"
    assert result.items[1].actor is None
    assert result.items[1].actor_label == "System"
    sql = captured["sql"]
    assert "bookings.class_session_id =" in sql
    assert "LEFT OUTER JOIN users AS" in sql
    assert "booking_events.created_at DESC, booking_events.id DESC" in sql
