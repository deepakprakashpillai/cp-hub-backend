from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.batch_groups.models import BatchGroup
from app.modules.bookings.models import Booking
from app.modules.classes.models import ClassSession
from app.modules.leads.models import Lead
from app.modules.read_models.admin_schemas import (
    AdminDashboardActionItems,
    AdminDashboardBatchGroupSummary,
    AdminDashboardBookingSummary,
    AdminDashboardClassSummary,
    AdminDashboardPaymentSummary,
    AdminDashboardStudentSummary,
    AdminDashboardSummaryRead,
    AdminDashboardTeacherSummary,
    AdminDashboardWindowRead,
    AdminStudentAccessState,
)
from app.modules.student_payments.models import StudentPayment
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.shared.enums import (
    BookingStatus,
    ClassSessionStatus,
    LeadStatus,
    StudentStatus,
)
from app.shared.utils import utc_now


class _ServiceBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class AdminDashboardQueryService(_ServiceBase):
    async def get_dashboard_summary(
        self,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
        now: datetime | None = None,
    ) -> AdminDashboardSummaryRead:
        generated_at = now or utc_now()
        starts_from, starts_to = _resolve_dashboard_window(
            starts_from=starts_from,
            starts_to=starts_to,
            now=generated_at,
        )

        student_total = await self._count_rows(Student)
        student_status_counts = await self._count_grouped(Student.status)
        active_with_valid_access = await self._count_rows(
            Student,
            Student.status == StudentStatus.ACTIVE,
            Student.access_starts_at <= generated_at,
            Student.access_ends_at > generated_at,
        )
        expired_access = await self._count_rows(
            Student,
            Student.status == StudentStatus.ACTIVE,
            Student.access_ends_at <= generated_at,
        )
        no_access = await self._count_rows(
            Student,
            Student.status == StudentStatus.ACTIVE,
            or_(
                Student.access_starts_at.is_(None),
                Student.access_ends_at.is_(None),
            ),
        )
        unconverted_enrolled_leads = await self._count_rows(
            Lead,
            Lead.status == LeadStatus.ENROLLED,
            Lead.converted_student_id.is_(None),
        )
        attendance_due = await self._count_rows(
            ClassSession,
            ClassSession.status == ClassSessionStatus.SCHEDULED,
            ClassSession.starts_at <= generated_at,
        )

        teacher_total = await self._count_rows(Teacher)
        teacher_active_counts = await self._count_grouped(Teacher.is_active)

        batch_group_total = await self._count_rows(BatchGroup)
        batch_group_active_counts = await self._count_grouped(BatchGroup.is_active)

        class_status_counts = await self._count_grouped(
            ClassSession.status,
            ClassSession.starts_at >= starts_from,
            ClassSession.starts_at < starts_to,
        )
        booking_status_counts = await self._count_grouped(
            Booking.status,
            Booking.booked_at >= starts_from,
            Booking.booked_at < starts_to,
        )
        payment_count, total_amount_paid = await self._payment_summary(starts_from, starts_to)

        return AdminDashboardSummaryRead(
            window=AdminDashboardWindowRead(
                starts_from=starts_from,
                starts_to=starts_to,
                generated_at=generated_at,
            ),
            students=AdminDashboardStudentSummary(
                total=student_total,
                active=student_status_counts.get(StudentStatus.ACTIVE, 0),
                enrolled=student_status_counts.get(StudentStatus.ENROLLED, 0),
                paused=student_status_counts.get(StudentStatus.PAUSED, 0),
                completed=student_status_counts.get(StudentStatus.COMPLETED, 0),
                cancelled=student_status_counts.get(StudentStatus.CANCELLED, 0),
                active_with_valid_access=active_with_valid_access,
                expired_access=expired_access,
            ),
            teachers=AdminDashboardTeacherSummary(
                total=teacher_total,
                active=teacher_active_counts.get(True, 0),
                inactive=teacher_active_counts.get(False, 0),
            ),
            batch_groups=AdminDashboardBatchGroupSummary(
                total=batch_group_total,
                active=batch_group_active_counts.get(True, 0),
                inactive=batch_group_active_counts.get(False, 0),
            ),
            classes=AdminDashboardClassSummary(
                scheduled=class_status_counts.get(ClassSessionStatus.SCHEDULED, 0),
                completed=class_status_counts.get(ClassSessionStatus.COMPLETED, 0),
                cancelled=class_status_counts.get(ClassSessionStatus.CANCELLED, 0),
            ),
            bookings=AdminDashboardBookingSummary(
                booked=booking_status_counts.get(BookingStatus.BOOKED, 0),
                cancelled=booking_status_counts.get(BookingStatus.CANCELLED, 0),
                attended=booking_status_counts.get(BookingStatus.ATTENDED, 0),
                missed=booking_status_counts.get(BookingStatus.MISSED, 0),
            ),
            payments=AdminDashboardPaymentSummary(
                count=payment_count,
                total_amount_paid=total_amount_paid,
            ),
            action_items=AdminDashboardActionItems(
                no_access=no_access,
                expired_access=expired_access,
                unconverted_enrolled_leads=unconverted_enrolled_leads,
                attendance_due=attendance_due,
            ),
        )

    async def _count_rows(self, model, *where_clauses) -> int:
        statement = select(func.count()).select_from(model)
        if where_clauses:
            statement = statement.where(*where_clauses)
        return await self.session.scalar(statement) or 0

    async def _count_grouped(self, column, *where_clauses) -> dict:
        statement = select(column, func.count()).group_by(column)
        if where_clauses:
            statement = statement.where(*where_clauses)
        result = await self.session.execute(statement)
        return {key: count for key, count in result.all()}

    async def _payment_summary(self, starts_from: datetime, starts_to: datetime) -> tuple[int, int]:
        statement = select(
            func.count(StudentPayment.id),
            func.coalesce(func.sum(StudentPayment.amount_paid), 0),
        ).where(
            StudentPayment.paid_at >= starts_from,
            StudentPayment.paid_at < starts_to,
        )
        result = await self.session.execute(statement)
        payment_count, total_amount_paid = result.one()
        return int(payment_count), int(total_amount_paid)


def _resolve_dashboard_window(
    *,
    starts_from: datetime | None,
    starts_to: datetime | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    if starts_from is None:
        starts_from = datetime.combine(now.date(), time.min, tzinfo=UTC)
    if starts_to is None:
        starts_to = starts_from + timedelta(days=1)
    if starts_from >= starts_to:
        raise ValueError("starts_from must be before starts_to")
    return starts_from, starts_to


def _normalize_search_query(q: str | None) -> str | None:
    if q is None:
        return None
    normalized = q.strip()
    return normalized or None


def _model_values(model) -> dict:
    return {key: value for key, value in vars(model).items() if not key.startswith("_")}


def _student_access_state_clause(access_state: AdminStudentAccessState, now: datetime):
    if access_state == AdminStudentAccessState.VALID:
        return (
            Student.access_starts_at.is_not(None)
            & (Student.access_starts_at <= now)
            & Student.access_ends_at.is_not(None)
            & (Student.access_ends_at > now)
        )
    if access_state == AdminStudentAccessState.EXPIRED:
        return Student.access_ends_at.is_not(None) & (Student.access_ends_at <= now)
    if access_state == AdminStudentAccessState.NOT_STARTED:
        return Student.access_starts_at.is_not(None) & (Student.access_starts_at > now)
    return or_(Student.access_starts_at.is_(None), Student.access_ends_at.is_(None))
