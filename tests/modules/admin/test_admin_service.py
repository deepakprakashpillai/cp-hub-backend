from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.core.exceptions import BadRequestError
from app.core.pagination import PaginationParams
from app.modules.admin.schemas import (
    AdminPaymentCreate,
    AdminStudentAccessGrantCreate,
    AdminStudentAccessState,
    AdminStudentBatchGroupSet,
    AdminStudentCreate,
    AdminStudentPaymentCreate,
    AdminStudentPaymentUpdate,
    AdminStudentSortBy,
    AdminStudentUpdate,
    AdminTeacherCreate,
    AdminTeacherSortBy,
    SortOrder,
)
from app.modules.admin.service import AdminService
from app.modules.batch_groups.schemas import (
    BatchGroupUpdate,
    BatchSessionBulkGenerate,
    StudentBatchTransfer,
)
from app.modules.batch_groups.service import BatchGroupService
from app.modules.booking_notes.service import BookingNoteService
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
from app.modules.schedules.schemas import (
    TeacherAvailabilityBlockCreate,
    TeacherAvailabilityRuleCreate,
    TeacherAvailabilityRuleUpdate,
    TeacherAvailabilitySlotBulkCreate,
    TeacherAvailabilitySlotCreate,
    TeacherAvailabilitySlotUpdate,
)
from app.modules.schedules.service import ScheduleService
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
    AvailabilitySlotSource,
    AvailabilitySlotStatus,
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


def test_admin_payment_create_requires_student_and_normalizes_paid_at() -> None:
    student_id = uuid4()
    payment = AdminPaymentCreate(
        student_id=student_id,
        amount_paid=50000,
        payment_method=PaymentMethod.UPI,
        paid_at=datetime.fromisoformat("2026-07-20T10:00:00+05:30"),
    )

    assert payment.student_id == student_id
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
        sql = str(statement.compile(dialect=postgresql.dialect()))
        assert "students.created_at DESC NULLS LAST" in sql
        return [(student, user, None, None)], 11

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    page = await AdminService(session).list_students(pagination)

    assert page.total == 11
    assert page.page == 2
    assert page.page_size == 10
    assert page.items[0].student.id == student.id
    assert page.items[0].user.email == "student@example.com"


@pytest.mark.asyncio
async def test_admin_student_get_returns_assigned_teacher_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student_user = User(
        id=uuid4(),
        full_name="Student One",
        email="student@example.com",
        role=UserRole.STUDENT,
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    teacher_user = User(
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
        user_id=teacher_user.id,
        display_name="Teacher One",
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    student = Student(
        id=uuid4(),
        user_id=student_user.id,
        program_type=StudentProgramType.ONE_ON_ONE,
        assigned_teacher_id=teacher.id,
        status=StudentStatus.ENROLLED,
        joined_at=timestamp(),
        created_at=timestamp(),
        updated_at=timestamp(),
    )

    async def fake_get_student(self, student_id):
        assert student_id == student.id
        return student

    async def fake_get_teacher(self, teacher_id):
        assert teacher_id == teacher.id
        return teacher

    async def fake_get_user(self, user_id):
        return student_user if user_id == student_user.id else teacher_user

    monkeypatch.setattr(StudentService, "get_student", fake_get_student)
    monkeypatch.setattr(TeacherService, "get_teacher", fake_get_teacher)
    monkeypatch.setattr(UserService, "get_user", fake_get_user)

    result = await AdminService(session).get_student(student.id)

    assert result.student.assigned_teacher_id == teacher.id
    assert result.assigned_teacher is not None
    assert result.assigned_teacher.teacher.id == teacher.id
    assert result.assigned_teacher.user.full_name == "Teacher One"


@pytest.mark.asyncio
async def test_admin_student_update_assigns_active_teacher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student_user = User(
        id=uuid4(),
        full_name="Student One",
        email="student@example.com",
        role=UserRole.STUDENT,
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    teacher_user = User(
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
        user_id=teacher_user.id,
        display_name="Teacher One",
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    student = Student(
        id=uuid4(),
        user_id=student_user.id,
        program_type=StudentProgramType.ONE_ON_ONE,
        status=StudentStatus.ENROLLED,
        joined_at=timestamp(),
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    assigned_ids = []

    async def fake_get_student(self, student_id):
        return student

    async def fake_get_teacher(self, teacher_id):
        return teacher

    async def fake_set_assigned_teacher(self, student_id, assigned_teacher_id):
        assigned_ids.append(assigned_teacher_id)
        student.assigned_teacher_id = assigned_teacher_id
        return student

    async def fake_get_user(self, user_id):
        return student_user if user_id == student_user.id else teacher_user

    monkeypatch.setattr(StudentService, "get_student", fake_get_student)
    monkeypatch.setattr(StudentService, "set_assigned_teacher", fake_set_assigned_teacher)
    monkeypatch.setattr(TeacherService, "get_teacher", fake_get_teacher)
    monkeypatch.setattr(UserService, "get_user", fake_get_user)

    result = await AdminService(session).update_student(
        student.id,
        AdminStudentUpdate(assigned_teacher_id=teacher.id),
    )

    assert assigned_ids == [teacher.id]
    assert result.assigned_teacher is not None
    assert result.assigned_teacher.teacher.id == teacher.id


@pytest.mark.asyncio
async def test_admin_student_update_rejects_teacher_for_batch_student(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student = Student(
        id=uuid4(),
        user_id=uuid4(),
        program_type=StudentProgramType.BATCH,
        status=StudentStatus.ENROLLED,
        joined_at=timestamp(),
        created_at=timestamp(),
        updated_at=timestamp(),
    )

    async def fake_get_student(self, student_id):
        return student

    monkeypatch.setattr(StudentService, "get_student", fake_get_student)

    with pytest.raises(BadRequestError, match="only valid for one-on-one"):
        await AdminService(session).update_student(
            student.id,
            AdminStudentUpdate(assigned_teacher_id=uuid4()),
        )


@pytest.mark.asyncio
async def test_student_assigned_teacher_can_be_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student = Student(
        id=uuid4(),
        user_id=uuid4(),
        program_type=StudentProgramType.ONE_ON_ONE,
        assigned_teacher_id=uuid4(),
        status=StudentStatus.ENROLLED,
        joined_at=timestamp(),
        created_at=timestamp(),
        updated_at=timestamp(),
    )

    async def fake_get_student(self, student_id):
        return student

    monkeypatch.setattr(StudentService, "get_student", fake_get_student)

    updated = await StudentService(session).set_assigned_teacher(student.id, None)

    assert updated.assigned_teacher_id is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_student_assigned_teacher_must_be_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student = Student(
        id=uuid4(),
        user_id=uuid4(),
        program_type=StudentProgramType.ONE_ON_ONE,
        status=StudentStatus.ENROLLED,
        joined_at=timestamp(),
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    teacher = Teacher(
        id=uuid4(),
        user_id=uuid4(),
        display_name="Inactive Teacher",
        is_active=False,
        created_at=timestamp(),
        updated_at=timestamp(),
    )
    session.get = AsyncMock(return_value=teacher)

    async def fake_get_student(self, student_id):
        return student

    monkeypatch.setattr(StudentService, "get_student", fake_get_student)

    with pytest.raises(BadRequestError, match="must be active"):
        await StudentService(session).set_assigned_teacher(student.id, teacher.id)


@pytest.mark.asyncio
async def test_admin_student_list_sorts_by_name_ascending(
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

    await AdminService(session).list_students(
        pagination,
        sort_by=AdminStudentSortBy.NAME,
        sort_order=SortOrder.ASC,
    )

    assert "users.full_name ASC NULLS LAST" in captured["sql"]


@pytest.mark.asyncio
async def test_admin_student_list_applies_search_and_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    pagination = PaginationParams(page=1, page_size=25)
    batch_group_id = uuid4()
    assigned_teacher_id = uuid4()
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
        assigned_teacher_id=assigned_teacher_id,
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
    assert "students.assigned_teacher_id =" in sql


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
        sql = str(statement.compile(dialect=postgresql.dialect()))
        assert "teachers.created_at DESC NULLS LAST" in sql
        assert "teachers.id ASC" in sql
        return [(teacher, user)], 1

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    page = await AdminService(session).list_teachers(pagination)

    assert page.total == 1
    assert page.items[0].teacher.id == teacher.id
    assert page.items[0].user.full_name == "Teacher One"


@pytest.mark.asyncio
async def test_admin_teacher_list_applies_search_and_independent_active_filters(
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
        account_is_active=True,
    )

    sql = captured["sql"]
    assert page.total == 0
    assert "teachers.display_name ILIKE" in sql
    assert "users.full_name ILIKE" in sql
    assert "users.email ILIKE" in sql
    assert "users.phone ILIKE" in sql
    assert "teachers.is_active IS false" in sql
    assert "users.is_active IS true" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sort_by", "sort_order", "expected_order"),
    [
        (
            AdminTeacherSortBy.CREATED_AT,
            SortOrder.ASC,
            "teachers.created_at ASC NULLS LAST",
        ),
        (
            AdminTeacherSortBy.CREATED_AT,
            SortOrder.DESC,
            "teachers.created_at DESC NULLS LAST",
        ),
        (
            AdminTeacherSortBy.NAME,
            SortOrder.ASC,
            "users.full_name ASC NULLS LAST",
        ),
        (
            AdminTeacherSortBy.NAME,
            SortOrder.DESC,
            "users.full_name DESC NULLS LAST",
        ),
        (
            AdminTeacherSortBy.DISPLAY_NAME,
            SortOrder.ASC,
            "teachers.display_name ASC NULLS LAST",
        ),
        (
            AdminTeacherSortBy.DISPLAY_NAME,
            SortOrder.DESC,
            "teachers.display_name DESC NULLS LAST",
        ),
        (
            AdminTeacherSortBy.IS_ACTIVE,
            SortOrder.ASC,
            "teachers.is_active ASC NULLS LAST",
        ),
        (
            AdminTeacherSortBy.IS_ACTIVE,
            SortOrder.DESC,
            "teachers.is_active DESC NULLS LAST",
        ),
    ],
)
async def test_admin_teacher_list_supports_whitelisted_sorting(
    monkeypatch: pytest.MonkeyPatch,
    sort_by: AdminTeacherSortBy,
    sort_order: SortOrder,
    expected_order: str,
) -> None:
    session = FakeSession()
    pagination = PaginationParams(page=1, page_size=25)
    captured = {}

    async def fake_paginate_rows(received_session, statement, received_pagination):
        captured["sql"] = str(statement.compile(dialect=postgresql.dialect()))
        return [], 0

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    await AdminService(session).list_teachers(
        pagination,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    assert expected_order in captured["sql"]
    assert "teachers.id ASC" in captured["sql"]


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
async def test_student_program_switch_to_batch_clears_assigned_teacher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    session.add = Mock()
    student = Student(
        id=uuid4(),
        user_id=uuid4(),
        program_type=StudentProgramType.ONE_ON_ONE,
        assigned_teacher_id=uuid4(),
        status=StudentStatus.ENROLLED,
        joined_at=timestamp(),
        created_at=timestamp(),
        updated_at=timestamp(),
    )

    async def fake_get_student(self, student_id):
        return student

    async def fake_cancel_future_bookings(self, **kwargs):
        return 0

    monkeypatch.setattr(StudentService, "get_student", fake_get_student)
    monkeypatch.setattr(
        BookingService,
        "cancel_future_bookings_for_student",
        fake_cancel_future_bookings,
    )

    await StudentService(session).switch_program(
        student.id,
        StudentProgramSwitch(new_program_type=StudentProgramType.BATCH),
    )

    assert student.program_type == StudentProgramType.BATCH
    assert student.assigned_teacher_id is None


@pytest.mark.asyncio
async def test_teacher_deactivation_clears_student_assignments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    session.execute = AsyncMock()
    teacher = Teacher(
        id=uuid4(),
        user_id=uuid4(),
        display_name="Teacher One",
        is_active=True,
        created_at=timestamp(),
        updated_at=timestamp(),
    )

    async def fake_get_teacher(self, teacher_id):
        return teacher

    monkeypatch.setattr(TeacherService, "get_teacher", fake_get_teacher)

    await TeacherService(session).update_teacher(
        teacher.id,
        TeacherUpdate(is_active=False),
    )

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "UPDATE students SET assigned_teacher_id=" in sql
    assert "students.assigned_teacher_id =" in sql
    assert teacher.is_active is False


@pytest.mark.asyncio
async def test_admin_teacher_schedule_aliases_delegate_to_schedule_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    pagination = PaginationParams(page=1, page_size=25)
    teacher_id = uuid4()
    rule_id = uuid4()
    slot_id = uuid4()
    starts_from = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    starts_to = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    rule_in = TeacherAvailabilityRuleCreate(
        teacher_id=teacher_id,
        day_of_week=DayOfWeek.WEDNESDAY,
        start_time_utc=time(8, 0),
        end_time_utc=time(9, 0),
        slot_duration_minutes=60,
    )
    slot_in = TeacherAvailabilitySlotCreate(
        teacher_id=teacher_id,
        rule_id=None,
        source=AvailabilitySlotSource.MANUAL,
        starts_at=starts_from,
        ends_at=starts_to,
        status=AvailabilitySlotStatus.AVAILABLE,
    )
    generation_result = SimpleNamespace(
        rules_checked=1,
        slots_created=2,
        slots_cancelled=3,
        slots_skipped=4,
    )
    calls = {}

    async def fake_list_rules(self, received_pagination, teacher_id=None):
        calls["list_rules"] = (received_pagination, teacher_id)
        return object()

    async def fake_create_rule(self, received_rule_in):
        calls["create_rule"] = received_rule_in
        return object()

    async def fake_get_rule(self, received_rule_id):
        calls["get_rule"] = received_rule_id
        return object()

    async def fake_update_rule(self, received_rule_id, received_rule_in):
        calls["update_rule"] = (received_rule_id, received_rule_in)
        return object()

    async def fake_delete_rule(self, received_rule_id):
        calls["delete_rule"] = received_rule_id

    async def fake_list_slots(
        self,
        received_pagination,
        teacher_id=None,
        starts_from=None,
        starts_to=None,
        status=None,
        source=None,
        descending=False,
    ):
        calls["list_slots"] = (
            received_pagination,
            teacher_id,
            starts_from,
            starts_to,
            status,
            source,
            descending,
        )
        return object()

    async def fake_create_slot(self, received_slot_in):
        calls["create_slot"] = received_slot_in
        return object()

    async def fake_create_slots_bulk(self, received_slots_in):
        calls["bulk_slots"] = received_slots_in
        return [object()]

    async def fake_create_block(self, received_block_in):
        calls["block"] = received_block_in
        return object()

    async def fake_get_slot(self, received_slot_id):
        calls["get_slot"] = received_slot_id
        return object()

    async def fake_update_slot(self, received_slot_id, received_slot_in):
        calls["update_slot"] = (received_slot_id, received_slot_in)
        return object()

    async def fake_delete_slot(self, received_slot_id):
        calls["delete_slot"] = received_slot_id

    async def fake_generate(self, received_teacher_id, *, days_ahead=14):
        calls["generate"] = (received_teacher_id, days_ahead)
        return generation_result

    monkeypatch.setattr(
        ScheduleService,
        "list_teacher_availability_rules",
        fake_list_rules,
    )
    monkeypatch.setattr(
        ScheduleService,
        "create_teacher_availability_rule",
        fake_create_rule,
    )
    monkeypatch.setattr(
        ScheduleService,
        "get_teacher_availability_rule",
        fake_get_rule,
    )
    monkeypatch.setattr(
        ScheduleService,
        "update_teacher_availability_rule",
        fake_update_rule,
    )
    monkeypatch.setattr(
        ScheduleService,
        "delete_teacher_availability_rule",
        fake_delete_rule,
    )
    monkeypatch.setattr(
        ScheduleService,
        "list_teacher_availability_slots",
        fake_list_slots,
    )
    monkeypatch.setattr(
        ScheduleService,
        "create_teacher_availability_slot",
        fake_create_slot,
    )
    monkeypatch.setattr(
        ScheduleService,
        "create_teacher_availability_slots_bulk",
        fake_create_slots_bulk,
    )
    monkeypatch.setattr(
        ScheduleService,
        "create_teacher_availability_block",
        fake_create_block,
    )
    monkeypatch.setattr(
        ScheduleService,
        "get_teacher_availability_slot",
        fake_get_slot,
    )
    monkeypatch.setattr(
        ScheduleService,
        "update_teacher_availability_slot",
        fake_update_slot,
    )
    monkeypatch.setattr(
        ScheduleService,
        "delete_teacher_availability_slot",
        fake_delete_slot,
    )
    monkeypatch.setattr(
        ScheduleService,
        "generate_teacher_availability_slots",
        fake_generate,
    )

    await AdminService(session).list_teacher_availability_rules(pagination, teacher_id=teacher_id)
    await AdminService(session).create_teacher_availability_rule(rule_in)
    await AdminService(session).get_teacher_availability_rule(rule_id)
    rule_update_in = TeacherAvailabilityRuleUpdate(slot_duration_minutes=30)
    await AdminService(session).update_teacher_availability_rule(rule_id, rule_update_in)
    await AdminService(session).delete_teacher_availability_rule(rule_id)
    await AdminService(session).list_teacher_availability_slots(
        pagination,
        teacher_id=teacher_id,
        starts_from=starts_from,
        starts_to=starts_to,
        status=AvailabilitySlotStatus.BLOCKED,
        source=AvailabilitySlotSource.MANUAL,
        sort_order=SortOrder.DESC,
    )
    await AdminService(session).create_teacher_availability_slot(slot_in)
    bulk_in = TeacherAvailabilitySlotBulkCreate(slots=[slot_in])
    await AdminService(session).create_teacher_availability_slots_bulk(bulk_in)
    block_in = TeacherAvailabilityBlockCreate(
        teacher_id=teacher_id,
        starts_at=starts_from + timedelta(hours=2),
        ends_at=starts_to + timedelta(hours=2),
    )
    await AdminService(session).create_teacher_availability_block(block_in)
    await AdminService(session).get_teacher_availability_slot(slot_id)
    slot_update_in = TeacherAvailabilitySlotUpdate(status=AvailabilitySlotStatus.CANCELLED)
    await AdminService(session).update_teacher_availability_slot(slot_id, slot_update_in)
    await AdminService(session).delete_teacher_availability_slot(slot_id)
    result = await AdminService(session).generate_teacher_availability_slots(
        teacher_id,
        days_ahead=30,
    )

    assert result is generation_result
    assert calls == {
        "list_rules": (pagination, teacher_id),
        "create_rule": rule_in,
        "get_rule": rule_id,
        "update_rule": (rule_id, rule_update_in),
        "delete_rule": rule_id,
        "list_slots": (
            pagination,
            teacher_id,
            starts_from,
            starts_to,
            AvailabilitySlotStatus.BLOCKED,
            AvailabilitySlotSource.MANUAL,
            True,
        ),
        "create_slot": slot_in,
        "bulk_slots": bulk_in,
        "block": block_in,
        "get_slot": slot_id,
        "update_slot": (slot_id, slot_update_in),
        "delete_slot": slot_id,
        "generate": (teacher_id, 30),
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
async def test_admin_package_void_delegates_to_package_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    package_id = uuid4()
    package = object()
    calls = {}

    async def fake_void_package(self, received_package_id):
        calls["package_id"] = received_package_id
        return package

    monkeypatch.setattr(PackageService, "void_package", fake_void_package)

    result = await AdminService(session).void_package(package_id)

    assert result is package
    assert calls == {"package_id": package_id}


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
    session.scalar = AsyncMock(side_effect=[100, 55, 8, 6, 4, 3, 12, 4])
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
    assert summary.action_items.no_access == 6
    assert summary.action_items.expired_access == 8
    assert summary.action_items.unconverted_enrolled_leads == 4
    assert summary.action_items.attendance_due == 3


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
async def test_admin_global_payment_create_uses_body_student_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student_id = uuid4()
    payment_id = uuid4()
    calls = {}

    async def fake_create_payment(self, payment_in):
        calls["student_id"] = payment_in.student_id
        return type("Payment", (), {"id": payment_id})()

    async def fake_get_payment(self, received_payment_id):
        calls["payment_id"] = received_payment_id
        return "payment-read"

    monkeypatch.setattr(StudentPaymentService, "create_payment", fake_create_payment)
    monkeypatch.setattr(AdminService, "get_payment", fake_get_payment)

    result = await AdminService(session).create_payment(
        AdminPaymentCreate(
            student_id=student_id,
            amount_paid=50000,
            payment_method=PaymentMethod.UPI,
        )
    )

    assert result == "payment-read"
    assert calls == {"student_id": student_id, "payment_id": payment_id}


@pytest.mark.asyncio
async def test_admin_student_payment_update_requires_path_student_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student_id = uuid4()
    payment_id = uuid4()
    payment = type("Payment", (), {"student_id": student_id})()
    updated_payment = object()
    calls = {}

    async def fake_get_payment(self, received_payment_id):
        calls["get_payment_id"] = received_payment_id
        return payment

    async def fake_update_payment(self, received_payment_id, payment_in):
        calls["update_payment_id"] = received_payment_id
        calls["payment_in"] = payment_in
        return updated_payment

    monkeypatch.setattr(StudentPaymentService, "get_payment", fake_get_payment)
    monkeypatch.setattr(StudentPaymentService, "update_payment", fake_update_payment)

    result = await AdminService(session).update_student_payment(
        student_id,
        payment_id,
        AdminStudentPaymentUpdate(amount_paid=60000),
    )

    assert result is updated_payment
    assert calls["get_payment_id"] == payment_id
    assert calls["update_payment_id"] == payment_id
    assert calls["payment_in"].student_id is None
    assert calls["payment_in"].amount_paid == 60000


@pytest.mark.asyncio
async def test_admin_student_payment_delete_requires_path_student_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    student_id = uuid4()
    payment_id = uuid4()
    payment = type("Payment", (), {"student_id": student_id})()
    calls = {}

    async def fake_get_payment(self, received_payment_id):
        calls["get_payment_id"] = received_payment_id
        return payment

    async def fake_delete_payment(self, received_payment_id):
        calls["delete_payment_id"] = received_payment_id

    monkeypatch.setattr(StudentPaymentService, "get_payment", fake_get_payment)
    monkeypatch.setattr(StudentPaymentService, "delete_payment", fake_delete_payment)

    await AdminService(session).delete_student_payment(student_id, payment_id)

    assert calls == {
        "get_payment_id": payment_id,
        "delete_payment_id": payment_id,
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
async def test_admin_booking_notes_delegates_to_booking_note_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    booking_id = uuid4()
    pagination = PaginationParams(page=1, page_size=25)
    expected = object()
    calls = {}

    async def fake_list_admin_booking_notes(
        self,
        received_booking_id,
        received_pagination,
    ):
        calls["booking_id"] = received_booking_id
        calls["pagination"] = received_pagination
        return expected

    monkeypatch.setattr(
        BookingNoteService,
        "list_admin_booking_notes",
        fake_list_admin_booking_notes,
    )

    result = await AdminService(session).list_booking_notes(booking_id, pagination)

    assert result is expected
    assert calls == {
        "booking_id": booking_id,
        "pagination": pagination,
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
    pagination = PaginationParams(page=1, page_size=25)
    starts_from = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    starts_to = datetime(2026, 7, 22, 18, 0, tzinfo=UTC)
    teacher_id = uuid4()
    batch_group_id = uuid4()
    captured = {}

    async def fake_paginate_rows(received_session, statement, received_pagination):
        captured["sql"] = str(statement.compile(dialect=postgresql.dialect()))
        assert received_session is session
        assert received_pagination is pagination
        return [], 0

    monkeypatch.setattr("app.modules.admin.service.paginate_rows", fake_paginate_rows)

    result = await AdminService(session).list_class_sessions(
        pagination,
        program_type=StudentProgramType.BATCH,
        starts_from=starts_from,
        starts_to=starts_to,
        status=ClassSessionStatus.SCHEDULED,
        teacher_id=teacher_id,
        batch_group_id=batch_group_id,
        sort_order=SortOrder.DESC,
    )

    assert result.items == []
    sql = captured["sql"]
    assert "class_sessions.program_type =" in sql
    assert "class_sessions.starts_at >=" in sql
    assert "class_sessions.starts_at <=" in sql
    assert "class_sessions.status =" in sql
    assert "class_sessions.teacher_id =" in sql
    assert "class_sessions.batch_group_id =" in sql
    assert "class_sessions.starts_at DESC" in sql
    assert "class_sessions.id ASC" in sql


@pytest.mark.asyncio
async def test_admin_batch_group_update_and_void_delegate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    batch_group_id = uuid4()
    updated_group = object()
    voided_group = object()
    calls = {}

    async def fake_update_batch_group(self, received_batch_group_id, batch_group_in):
        calls["update_id"] = received_batch_group_id
        calls["update_in"] = batch_group_in
        return updated_group

    async def fake_void_batch_group(self, received_batch_group_id):
        calls["void_id"] = received_batch_group_id
        return voided_group

    monkeypatch.setattr(BatchGroupService, "update_batch_group", fake_update_batch_group)
    monkeypatch.setattr(BatchGroupService, "void_batch_group", fake_void_batch_group)

    update_in = BatchGroupUpdate(name="Updated Batch")
    updated_result = await AdminService(session).update_batch_group(batch_group_id, update_in)

    assert updated_result is updated_group
    assert await AdminService(session).void_batch_group(batch_group_id) is voided_group
    assert calls == {
        "update_id": batch_group_id,
        "update_in": update_in,
        "void_id": batch_group_id,
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
async def test_admin_class_cancel_delegates_to_booking_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    class_session_id = uuid4()
    class_session = object()
    calls = {}

    async def fake_admin_cancel_class_session(self, received_class_session_id, cancel_in):
        calls["class_session_id"] = received_class_session_id
        calls["cancel_in"] = cancel_in
        return class_session

    monkeypatch.setattr(
        BookingService,
        "admin_cancel_class_session",
        fake_admin_cancel_class_session,
    )
    projected_class = object()

    async def fake_get_class_session(self, received_class_session_id):
        assert received_class_session_id == class_session_id
        return projected_class

    monkeypatch.setattr(AdminService, "get_class_session", fake_get_class_session)

    cancel_in = BookingActionRequest(reason="teacher unavailable")
    result = await AdminService(session).cancel_class_session(class_session_id, cancel_in)

    assert result is projected_class
    assert calls == {
        "class_session_id": class_session_id,
        "cancel_in": cancel_in,
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
