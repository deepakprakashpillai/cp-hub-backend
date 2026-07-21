from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.core.pagination import PaginationParams
from app.modules.admin.schemas import (
    AdminStudentAccessGrantCreate,
    AdminStudentAccessState,
    AdminStudentBatchGroupSet,
    AdminStudentCreate,
    AdminStudentPaymentCreate,
    AdminTeacherCreate,
)
from app.modules.admin.service import AdminService
from app.modules.batch_groups.schemas import BatchSessionBulkGenerate, StudentBatchTransfer
from app.modules.batch_groups.service import BatchGroupService
from app.modules.bookings.schemas import (
    AdminAddStudentToClass,
    BatchBookingReschedule,
    BookingActionRequest,
    ClassAttendanceMark,
    ClassAttendanceRecord,
    OneOnOneBookingReschedule,
)
from app.modules.bookings.service import BookingService
from app.modules.classes.schemas import BatchClassSessionCreate
from app.modules.classes.service import ClassSessionService
from app.modules.packages.schemas import PackageUpdate
from app.modules.packages.service import PackageService
from app.modules.student_access_grants.service import StudentAccessGrantService
from app.modules.student_payments.service import StudentPaymentService
from app.modules.students.models import Student
from app.modules.students.schemas import StudentProgramSwitch, StudentUpdate
from app.modules.students.service import StudentService
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherUpdate
from app.modules.teachers.service import TeacherService
from app.modules.users.models import User
from app.modules.users.schemas import UserUpdate
from app.modules.users.service import UserService
from app.shared.enums import (
    BatchSlot,
    BookingStatus,
    ClassSessionStatus,
    DayOfWeek,
    PaymentMethod,
    StudentAccessGrantType,
    StudentProgramType,
    StudentStatus,
    UserRole,
)


class FakeSession:
    def __init__(self) -> None:
        self.commit = AsyncMock()
        self.refresh = AsyncMock()


class FakeResult:
    def __init__(self, *, rows=None, one_row=None) -> None:
        self.rows = rows or []
        self.one_row = one_row

    def all(self):
        return self.rows

    def one(self):
        return self.one_row


def timestamp() -> datetime:
    return datetime(2026, 7, 20, tzinfo=UTC)


def test_admin_student_create_normalizes_access_datetimes_to_utc() -> None:
    student = AdminStudentCreate(
        full_name="Student One",
        email="student@example.com",
        program_type=StudentProgramType.ONE_ON_ONE,
        access_starts_at=datetime.fromisoformat("2026-07-20T00:00:00+05:30"),
        access_ends_at=datetime.fromisoformat("2026-08-19T00:00:00+05:30"),
    )

    assert student.is_active is True
    assert student.status == StudentStatus.ENROLLED
    assert student.access_starts_at == datetime(2026, 7, 19, 18, 30, tzinfo=UTC)
    assert student.access_ends_at == datetime(2026, 8, 18, 18, 30, tzinfo=UTC)


def test_admin_student_create_rejects_naive_access_datetime() -> None:
    with pytest.raises(ValidationError, match="datetime must include timezone info"):
        AdminStudentCreate(
            full_name="Student One",
            email="student@example.com",
            program_type=StudentProgramType.BATCH,
            access_starts_at=datetime(2026, 7, 20),
        )


def test_admin_student_payment_create_normalizes_paid_at_to_utc() -> None:
    payment = AdminStudentPaymentCreate(
        amount_paid=50000,
        payment_method=PaymentMethod.UPI,
        paid_at=datetime.fromisoformat("2026-07-20T10:00:00+05:30"),
    )

    assert payment.currency == "INR"
    assert payment.paid_at == datetime(2026, 7, 20, 4, 30, tzinfo=UTC)


def test_admin_student_access_grant_create_normalizes_start_to_utc() -> None:
    grant = AdminStudentAccessGrantCreate(
        grant_type=StudentAccessGrantType.ADDON_DAYS,
        duration_days=7,
        access_starts_at=datetime.fromisoformat("2026-07-20T00:00:00+05:30"),
    )

    assert grant.extend_current_access is True
    assert grant.access_starts_at == datetime(2026, 7, 19, 18, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_admin_student_list_returns_nested_user_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    user = User(
        id=uuid4(),
        full_name="Student One",
        email="student@example.com",
        role=UserRole.STUDENT,
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    student = Student(
        id=uuid4(),
        user_id=user.id,
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ENROLLED,
        joined_at=timestamp(),
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    pagination = PaginationParams(page=2, page_size=10)

    async def fake_paginate_rows(received_session, statement, received_pagination):
        assert received_session is session
        assert received_pagination is pagination
        return [(student, user)], 11

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    page = await AdminService(session).list_students(pagination)

    assert page.total == 11
    assert page.page == 2
    assert page.page_size == 10
    assert page.items[0].student.id == student.id
    assert page.items[0].user.email == "student@example.com"


@pytest.mark.asyncio
async def test_admin_student_list_applies_search_and_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    pagination = PaginationParams(page=1, page_size=25)
    batch_group_id = uuid4()
    captured = {}

    async def fake_paginate_rows(received_session, statement, received_pagination):
        captured["sql"] = str(statement.compile(dialect=postgresql.dialect()))
        assert received_session is session
        assert received_pagination is pagination
        return [], 0

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    page = await AdminService(session).list_students(
        pagination,
        q=" deepak ",
        status=StudentStatus.ACTIVE,
        program_type=StudentProgramType.BATCH,
        access_state=AdminStudentAccessState.VALID,
        batch_group_id=batch_group_id,
    )

    sql = captured["sql"]
    assert page.total == 0
    assert "users.full_name ILIKE" in sql
    assert "users.email ILIKE" in sql
    assert "users.phone ILIKE" in sql
    assert "students.status" in sql
    assert "students.program_type" in sql
    assert "students.access_starts_at" in sql
    assert "students.access_ends_at" in sql
    assert "EXISTS" in sql
    assert "student_batch_memberships" in sql


@pytest.mark.asyncio
async def test_admin_teacher_list_returns_nested_user_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    user = User(
        id=uuid4(),
        full_name="Teacher One",
        email="teacher@example.com",
        role=UserRole.TEACHER,
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    teacher = Teacher(
        id=uuid4(),
        user_id=user.id,
        display_name="Teacher One",
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    pagination = PaginationParams(page=1, page_size=25)

    async def fake_paginate_rows(received_session, statement, received_pagination):
        assert received_session is session
        assert received_pagination is pagination
        return [(teacher, user)], 1

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    page = await AdminService(session).list_teachers(pagination)

    assert page.total == 1
    assert page.items[0].teacher.id == teacher.id
    assert page.items[0].user.full_name == "Teacher One"


@pytest.mark.asyncio
async def test_admin_teacher_list_applies_search_and_active_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    pagination = PaginationParams(page=1, page_size=25)
    captured = {}

    async def fake_paginate_rows(received_session, statement, received_pagination):
        captured["sql"] = str(statement.compile(dialect=postgresql.dialect()))
        assert received_session is session
        assert received_pagination is pagination
        return [], 0

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    page = await AdminService(session).list_teachers(
        pagination,
        q=" teacher ",
        is_active=False,
    )

    sql = captured["sql"]
    assert page.total == 0
    assert "teachers.display_name ILIKE" in sql
    assert "users.full_name ILIKE" in sql
    assert "users.email ILIKE" in sql
    assert "users.phone ILIKE" in sql
    assert "teachers.is_active IS false" in sql


@pytest.mark.asyncio
async def test_admin_student_update_uses_program_switch_for_program_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student_id = uuid4()
    user = User(
        id=uuid4(),
        full_name="Student One",
        email="student@example.com",
        role=UserRole.STUDENT,
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    before_switch = Student(
        id=student_id,
        user_id=user.id,
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ACTIVE,
        access_starts_at=timestamp(),
        access_ends_at=timestamp() + timedelta(days=30),
        joined_at=timestamp(),
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    after_switch = Student(
        id=student_id,
        user_id=user.id,
        program_type=StudentProgramType.ONE_ON_ONE,
        status=StudentStatus.ACTIVE,
        access_starts_at=timestamp(),
        access_ends_at=timestamp() + timedelta(days=30),
        joined_at=timestamp(),
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    calls = {}

    async def fake_update_student(self, received_student_id, student_in):
        calls["update_student_id"] = received_student_id
        calls["update_in"] = student_in
        return before_switch

    async def fake_switch_program(self, received_student_id, switch_in):
        calls["switch_student_id"] = received_student_id
        calls["switch_in"] = switch_in
        return object()

    async def fake_get_student(self, received_student_id):
        calls["get_student_id"] = received_student_id
        return after_switch

    async def fake_get_user(self, received_user_id):
        calls["user_id"] = received_user_id
        return user

    monkeypatch.setattr(StudentService, "update_student", fake_update_student)
    monkeypatch.setattr(StudentService, "switch_program", fake_switch_program)
    monkeypatch.setattr(StudentService, "get_student", fake_get_student)
    monkeypatch.setattr(UserService, "get_user", fake_get_user)

    result = await AdminService(session).update_student(
        student_id,
        StudentUpdate(
            program_type=StudentProgramType.ONE_ON_ONE,
            status=StudentStatus.ACTIVE,
        ),
    )

    assert result.student.program_type == StudentProgramType.ONE_ON_ONE
    assert result.user.id == user.id
    assert calls["update_student_id"] == student_id
    assert calls["update_in"] == StudentUpdate(status=StudentStatus.ACTIVE)
    assert calls["switch_student_id"] == student_id
    assert calls["switch_in"] == StudentProgramSwitch(
        new_program_type=StudentProgramType.ONE_ON_ONE
    )
    assert calls["get_student_id"] == student_id
    assert calls["user_id"] == user.id


@pytest.mark.asyncio
async def test_admin_teacher_update_returns_nested_user_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    user = User(
        id=uuid4(),
        full_name="Teacher One",
        email="teacher@example.com",
        role=UserRole.TEACHER,
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    teacher = Teacher(
        id=uuid4(),
        user_id=user.id,
        display_name="Teacher Updated",
        is_active=False,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    calls = {}

    async def fake_update_teacher(self, received_teacher_id, teacher_in):
        calls["teacher_id"] = received_teacher_id
        calls["teacher_in"] = teacher_in
        return teacher

    async def fake_get_user(self, received_user_id):
        calls["user_id"] = received_user_id
        return user

    monkeypatch.setattr(TeacherService, "update_teacher", fake_update_teacher)
    monkeypatch.setattr(UserService, "get_user", fake_get_user)

    result = await AdminService(session).update_teacher(
        teacher.id,
        TeacherUpdate(display_name="Teacher Updated", is_active=False),
    )

    assert result.teacher.display_name == "Teacher Updated"
    assert result.user.id == user.id
    assert calls == {
        "teacher_id": teacher.id,
        "teacher_in": TeacherUpdate(display_name="Teacher Updated", is_active=False),
        "user_id": user.id,
    }


@pytest.mark.asyncio
async def test_admin_package_update_delegates_to_package_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    package_id = uuid4()
    package = object()
    calls = {}

    async def fake_update_package(self, received_package_id, package_in):
        calls["package_id"] = received_package_id
        calls["package_in"] = package_in
        return package

    monkeypatch.setattr(PackageService, "update_package", fake_update_package)

    result = await AdminService(session).update_package(
        package_id,
        PackageUpdate(name="Updated IELTS"),
    )

    assert result is package
    assert calls == {
        "package_id": package_id,
        "package_in": PackageUpdate(name="Updated IELTS"),
    }


@pytest.mark.asyncio
async def test_admin_user_update_delegates_to_user_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    user = User(
        id=uuid4(),
        full_name="Updated User",
        email="updated@example.com",
        role=UserRole.STUDENT,
        is_active=False,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    calls = {}

    async def fake_update_user(self, received_user_id, user_in):
        calls["user_id"] = received_user_id
        calls["user_in"] = user_in
        return user

    monkeypatch.setattr(UserService, "update_user", fake_update_user)

    result = await AdminService(session).update_user(
        user.id,
        UserUpdate(full_name="Updated User", is_active=False),
    )

    assert result is user
    assert calls == {
        "user_id": user.id,
        "user_in": UserUpdate(full_name="Updated User", is_active=False),
    }


@pytest.mark.asyncio
async def test_admin_dashboard_summary_returns_aggregate_counts() -> None:
    session = FakeSession()
    session.scalar = AsyncMock(side_effect=[100, 55, 8, 12, 4])
    session.execute = AsyncMock(
        side_effect=[
            FakeResult(
                rows=[
                    (StudentStatus.ACTIVE, 70),
                    (StudentStatus.ENROLLED, 10),
                    (StudentStatus.PAUSED, 5),
                    (StudentStatus.COMPLETED, 12),
                    (StudentStatus.CANCELLED, 3),
                ]
            ),
            FakeResult(rows=[(True, 9), (False, 3)]),
            FakeResult(rows=[(True, 3), (False, 1)]),
            FakeResult(
                rows=[
                    (ClassSessionStatus.SCHEDULED, 6),
                    (ClassSessionStatus.COMPLETED, 2),
                    (ClassSessionStatus.CANCELLED, 1),
                ]
            ),
            FakeResult(
                rows=[
                    (BookingStatus.BOOKED, 7),
                    (BookingStatus.CANCELLED, 2),
                    (BookingStatus.ATTENDED, 5),
                ]
            ),
            FakeResult(one_row=(4, 125000)),
        ]
    )
    starts_from = datetime(2026, 7, 22, tzinfo=UTC)
    starts_to = starts_from + timedelta(days=1)
    now = datetime(2026, 7, 22, 8, 30, tzinfo=UTC)

    summary = await AdminService(session).get_dashboard_summary(
        starts_from=starts_from,
        starts_to=starts_to,
        now=now,
    )

    assert summary.window.starts_from == starts_from
    assert summary.window.starts_to == starts_to
    assert summary.window.generated_at == now
    assert summary.students.total == 100
    assert summary.students.active == 70
    assert summary.students.active_with_valid_access == 55
    assert summary.students.expired_access == 8
    assert summary.teachers.active == 9
    assert summary.teachers.inactive == 3
    assert summary.batch_groups.active == 3
    assert summary.classes.scheduled == 6
    assert summary.bookings.booked == 7
    assert summary.bookings.missed == 0
    assert summary.payments.count == 4
    assert summary.payments.total_amount_paid == 125000


@pytest.mark.asyncio
async def test_admin_dashboard_summary_rejects_inverted_window() -> None:
    session = FakeSession()
    starts_from = datetime(2026, 7, 23, tzinfo=UTC)
    starts_to = datetime(2026, 7, 22, tzinfo=UTC)

    with pytest.raises(ValueError, match="starts_from must be before starts_to"):
        await AdminService(session).get_dashboard_summary(
            starts_from=starts_from,
            starts_to=starts_to,
            now=starts_from,
        )


@pytest.mark.asyncio
async def test_admin_teacher_create_commits_once_after_user_and_teacher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    user = User(
        id=uuid4(),
        full_name="Teacher One",
        email="teacher@example.com",
        role=UserRole.TEACHER,
        is_active=True,
    )
    teacher = Teacher(
        id=uuid4(),
        user_id=user.id,
        display_name="Teacher One",
        is_active=True,
    )
    calls = {}

    async def fake_create_user(self, user_in, *, commit=True):
        calls["user_role"] = user_in.role
        calls["user_commit"] = commit
        return user

    async def fake_create_teacher(self, teacher_in, *, commit=True):
        calls["teacher_user_id"] = teacher_in.user_id
        calls["teacher_commit"] = commit
        return teacher

    monkeypatch.setattr(UserService, "create_user", fake_create_user)
    monkeypatch.setattr(TeacherService, "create_teacher", fake_create_teacher)

    created_user, created_teacher = await AdminService(session).create_teacher(
        AdminTeacherCreate(
            full_name="Teacher One",
            email="teacher@example.com",
            display_name="Teacher One",
        )
    )

    assert created_user is user
    assert created_teacher is teacher
    assert calls == {
        "user_role": UserRole.TEACHER,
        "user_commit": False,
        "teacher_user_id": user.id,
        "teacher_commit": False,
    }
    session.commit.assert_awaited_once()
    assert session.refresh.await_count == 2


@pytest.mark.asyncio
async def test_admin_student_payment_uses_path_student_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student_id = uuid4()
    payment = object()
    calls = {}

    async def fake_create_payment(self, payment_in):
        calls["student_id"] = payment_in.student_id
        calls["amount_paid"] = payment_in.amount_paid
        calls["payment_method"] = payment_in.payment_method
        return payment

    monkeypatch.setattr(StudentPaymentService, "create_payment", fake_create_payment)

    created_payment = await AdminService(session).create_student_payment(
        student_id,
        AdminStudentPaymentCreate(
            amount_paid=50000,
            payment_method=PaymentMethod.UPI,
        ),
    )

    assert created_payment is payment
    assert calls == {
        "student_id": student_id,
        "amount_paid": 50000,
        "payment_method": PaymentMethod.UPI,
    }


@pytest.mark.asyncio
async def test_admin_student_access_grant_uses_path_student_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student_id = uuid4()
    grant = object()
    calls = {}

    async def fake_create_grant(self, grant_in):
        calls["student_id"] = grant_in.student_id
        calls["grant_type"] = grant_in.grant_type
        calls["duration_days"] = grant_in.duration_days
        return grant

    monkeypatch.setattr(StudentAccessGrantService, "create_grant", fake_create_grant)

    created_grant = await AdminService(session).create_student_access_grant(
        student_id,
        AdminStudentAccessGrantCreate(
            grant_type=StudentAccessGrantType.ADDON_DAYS,
            duration_days=7,
        ),
    )

    assert created_grant is grant
    assert calls == {
        "student_id": student_id,
        "grant_type": StudentAccessGrantType.ADDON_DAYS,
        "duration_days": 7,
    }


@pytest.mark.asyncio
async def test_admin_student_batch_group_uses_transfer_logic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student_id = uuid4()
    batch_group_id = uuid4()
    actor_user_id = uuid4()
    membership = object()
    calls = {}

    async def fake_transfer_student_batch_group(self, received_student_id, transfer_in):
        calls["student_id"] = received_student_id
        calls["transfer_in"] = transfer_in
        return membership

    monkeypatch.setattr(
        BatchGroupService,
        "transfer_student_batch_group",
        fake_transfer_student_batch_group,
    )

    created_membership = await AdminService(session).set_student_batch_group(
        student_id,
        AdminStudentBatchGroupSet(
            batch_group_id=batch_group_id,
            assigned_by_user_id=actor_user_id,
            reason="set from admin portal",
        ),
    )

    assert created_membership is membership
    assert calls["student_id"] == student_id
    assert calls["transfer_in"] == StudentBatchTransfer(
        batch_group_id=batch_group_id,
        assigned_by_user_id=actor_user_id,
        reason="set from admin portal",
    )


@pytest.mark.asyncio
async def test_admin_student_program_switch_delegates_to_student_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student_id = uuid4()
    program_change = object()
    calls = {}

    async def fake_switch_program(self, received_student_id, switch_in):
        calls["student_id"] = received_student_id
        calls["switch_in"] = switch_in
        return program_change

    monkeypatch.setattr(StudentService, "switch_program", fake_switch_program)

    switch_in = StudentProgramSwitch(new_program_type=StudentProgramType.ONE_ON_ONE)
    created_change = await AdminService(session).switch_student_program(student_id, switch_in)

    assert created_change is program_change
    assert calls == {
        "student_id": student_id,
        "switch_in": switch_in,
    }


@pytest.mark.asyncio
async def test_admin_batch_session_generation_delegates_to_batch_group_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    batch_group_id = uuid4()
    class_sessions = [object(), object()]
    calls = {}

    async def fake_generate_batch_sessions(self, received_batch_group_id, generation_in):
        calls["batch_group_id"] = received_batch_group_id
        calls["generation_in"] = generation_in
        return class_sessions

    monkeypatch.setattr(BatchGroupService, "generate_batch_sessions", fake_generate_batch_sessions)

    generation_in = BatchSessionBulkGenerate(
        starts_from=datetime(2026, 7, 20, tzinfo=UTC).date(),
        starts_to=datetime(2026, 7, 21, tzinfo=UTC).date(),
        weekdays=[DayOfWeek.MONDAY],
        sessions=[
            {
                "batch_slot": BatchSlot.MORNING,
                "start_time_utc": "09:00:00",
                "end_time_utc": "10:00:00",
            }
        ],
    )
    result = await AdminService(session).generate_batch_sessions(batch_group_id, generation_in)

    assert result is class_sessions
    assert calls == {
        "batch_group_id": batch_group_id,
        "generation_in": generation_in,
    }


@pytest.mark.asyncio
async def test_admin_create_batch_class_delegates_to_class_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    class_session = object()
    calls = {}

    async def fake_create_batch_class_session(self, class_session_in):
        calls["class_session_in"] = class_session_in
        return class_session

    monkeypatch.setattr(
        ClassSessionService,
        "create_batch_class_session",
        fake_create_batch_class_session,
    )

    class_session_in = BatchClassSessionCreate(
        batch_group_id=uuid4(),
        batch_slot=BatchSlot.NOON,
        starts_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 11, 0, tzinfo=UTC),
        status=ClassSessionStatus.SCHEDULED,
        capacity=12,
    )
    result = await AdminService(session).create_batch_class_session(class_session_in)

    assert result is class_session
    assert calls == {"class_session_in": class_session_in}


@pytest.mark.asyncio
async def test_admin_class_list_delegates_with_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    class_sessions = object()
    pagination = PaginationParams(page=1, page_size=25)
    starts_from = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    starts_to = datetime(2026, 7, 22, 18, 0, tzinfo=UTC)
    teacher_id = uuid4()
    batch_group_id = uuid4()
    calls = {}

    async def fake_list_class_sessions(self, received_pagination, **filters):
        calls["pagination"] = received_pagination
        calls["filters"] = filters
        return class_sessions

    monkeypatch.setattr(ClassSessionService, "list_class_sessions", fake_list_class_sessions)

    result = await AdminService(session).list_class_sessions(
        pagination,
        program_type=StudentProgramType.BATCH,
        starts_from=starts_from,
        starts_to=starts_to,
        status=ClassSessionStatus.SCHEDULED,
        teacher_id=teacher_id,
        batch_group_id=batch_group_id,
    )

    assert result is class_sessions
    assert calls == {
        "pagination": pagination,
        "filters": {
            "program_type": StudentProgramType.BATCH,
            "starts_from": starts_from,
            "starts_to": starts_to,
            "status": ClassSessionStatus.SCHEDULED,
            "teacher_id": teacher_id,
            "batch_group_id": batch_group_id,
        },
    }


@pytest.mark.asyncio
async def test_admin_add_student_to_class_delegates_to_admin_booking_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    class_session_id = uuid4()
    booking = object()
    calls = {}

    async def fake_admin_add_student_to_class(self, received_class_session_id, add_in):
        calls["class_session_id"] = received_class_session_id
        calls["add_in"] = add_in
        return booking

    monkeypatch.setattr(
        BookingService,
        "admin_add_student_to_class",
        fake_admin_add_student_to_class,
    )

    add_in = AdminAddStudentToClass(student_id=uuid4(), reason="admin added")
    result = await AdminService(session).add_student_to_class(class_session_id, add_in)

    assert result is booking
    assert calls == {
        "class_session_id": class_session_id,
        "add_in": add_in,
    }


@pytest.mark.asyncio
async def test_admin_class_attendance_delegates_to_booking_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    class_session_id = uuid4()
    bookings = [object()]
    calls = {}

    async def fake_mark_class_attendance(self, received_class_session_id, attendance_in):
        calls["class_session_id"] = received_class_session_id
        calls["attendance_in"] = attendance_in
        return bookings

    monkeypatch.setattr(BookingService, "mark_class_attendance", fake_mark_class_attendance)

    attendance_in = ClassAttendanceMark(
        records=[ClassAttendanceRecord(booking_id=uuid4(), status=BookingStatus.ATTENDED)]
    )
    result = await AdminService(session).mark_class_attendance(class_session_id, attendance_in)

    assert result is bookings
    assert calls == {
        "class_session_id": class_session_id,
        "attendance_in": attendance_in,
    }


@pytest.mark.asyncio
async def test_admin_booking_cancel_delegates_to_admin_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    booking_id = uuid4()
    booking = object()
    calls = {}

    async def fake_admin_cancel_booking(self, received_booking_id, cancel_in):
        calls["booking_id"] = received_booking_id
        calls["cancel_in"] = cancel_in
        return booking

    monkeypatch.setattr(BookingService, "admin_cancel_booking", fake_admin_cancel_booking)

    cancel_in = BookingActionRequest(reason="admin cancellation")
    result = await AdminService(session).cancel_booking(booking_id, cancel_in)

    assert result is booking
    assert calls == {
        "booking_id": booking_id,
        "cancel_in": cancel_in,
    }


@pytest.mark.asyncio
async def test_admin_booking_list_delegates_with_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    bookings = object()
    pagination = PaginationParams(page=1, page_size=25)
    student_id = uuid4()
    class_session_id = uuid4()
    teacher_id = uuid4()
    starts_from = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    starts_to = datetime(2026, 7, 22, 18, 0, tzinfo=UTC)
    calls = {}

    async def fake_list_bookings(self, received_pagination, **filters):
        calls["pagination"] = received_pagination
        calls["filters"] = filters
        return bookings

    monkeypatch.setattr(BookingService, "list_bookings", fake_list_bookings)

    result = await AdminService(session).list_bookings(
        pagination,
        student_id=student_id,
        class_session_id=class_session_id,
        status=BookingStatus.BOOKED,
        teacher_id=teacher_id,
        starts_from=starts_from,
        starts_to=starts_to,
    )

    assert result is bookings
    assert calls == {
        "pagination": pagination,
        "filters": {
            "student_id": student_id,
            "class_session_id": class_session_id,
            "status": BookingStatus.BOOKED,
            "teacher_id": teacher_id,
            "starts_from": starts_from,
            "starts_to": starts_to,
        },
    }


@pytest.mark.asyncio
async def test_admin_one_on_one_reschedule_delegates_to_admin_reschedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    booking_id = uuid4()
    booking = object()
    calls = {}

    async def fake_admin_reschedule_one_on_one_booking(self, received_booking_id, reschedule_in):
        calls["booking_id"] = received_booking_id
        calls["reschedule_in"] = reschedule_in
        return booking

    monkeypatch.setattr(
        BookingService,
        "admin_reschedule_one_on_one_booking",
        fake_admin_reschedule_one_on_one_booking,
    )

    reschedule_in = OneOnOneBookingReschedule(teacher_availability_slot_id=uuid4())
    result = await AdminService(session).reschedule_one_on_one_booking(booking_id, reschedule_in)

    assert result is booking
    assert calls == {
        "booking_id": booking_id,
        "reschedule_in": reschedule_in,
    }


@pytest.mark.asyncio
async def test_admin_batch_reschedule_delegates_to_admin_reschedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    booking_id = uuid4()
    booking = object()
    calls = {}

    async def fake_admin_reschedule_batch_booking(self, received_booking_id, reschedule_in):
        calls["booking_id"] = received_booking_id
        calls["reschedule_in"] = reschedule_in
        return booking

    monkeypatch.setattr(
        BookingService,
        "admin_reschedule_batch_booking",
        fake_admin_reschedule_batch_booking,
    )

    reschedule_in = BatchBookingReschedule(class_session_id=uuid4())
    result = await AdminService(session).reschedule_batch_booking(booking_id, reschedule_in)

    assert result is booking
    assert calls == {
        "booking_id": booking_id,
        "reschedule_in": reschedule_in,
    }


@pytest.mark.asyncio
async def test_admin_student_create_commits_once_after_user_and_student(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    user = User(
        id=uuid4(),
        full_name="Student One",
        email="student@example.com",
        role=UserRole.STUDENT,
        is_active=True,
    )
    student = Student(
        id=uuid4(),
        user_id=user.id,
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ENROLLED,
    )
    calls = {}

    async def fake_create_user(self, user_in, *, commit=True):
        calls["user_role"] = user_in.role
        calls["user_commit"] = commit
        return user

    async def fake_create_student(self, student_in, *, commit=True):
        calls["student_user_id"] = student_in.user_id
        calls["student_program_type"] = student_in.program_type
        calls["student_commit"] = commit
        return student

    monkeypatch.setattr(UserService, "create_user", fake_create_user)
    monkeypatch.setattr(StudentService, "create_student", fake_create_student)

    created_user, created_student = await AdminService(session).create_student(
        AdminStudentCreate(
            full_name="Student One",
            email="student@example.com",
            program_type=StudentProgramType.BATCH,
        )
    )

    assert created_user is user
    assert created_student is student
    assert calls == {
        "user_role": UserRole.STUDENT,
        "user_commit": False,
        "student_user_id": user.id,
        "student_program_type": StudentProgramType.BATCH,
        "student_commit": False,
    }
    session.commit.assert_awaited_once()
    assert session.refresh.await_count == 2
