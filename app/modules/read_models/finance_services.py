from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_rows
from app.modules.packages.models import Package
from app.modules.read_models.admin_schemas import (
    AdminPaymentCreate,
    AdminPaymentCurrencySummary,
    AdminPaymentMethodSummary,
    AdminPaymentRead,
    AdminPaymentSortBy,
    AdminPaymentStudentSummary,
    AdminPaymentSummaryRead,
    AdminStudentAccessState,
    AdminStudentPaymentUpdate,
)
from app.modules.student_payments.models import StudentPayment
from app.modules.student_payments.schemas import StudentPaymentCreate, StudentPaymentUpdate
from app.modules.student_payments.service import StudentPaymentService
from app.modules.students.models import Student
from app.modules.users.models import User
from app.shared.enums import (
    PaymentMethod,
    SortOrder,
)


class _ServiceBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class AdminFinanceService(_ServiceBase):
    async def list_payments(
        self,
        pagination: PaginationParams,
        *,
        q: str | None = None,
        payment_method: PaymentMethod | None = None,
        package_id: UUID | None = None,
        currency: str | None = None,
        paid_from: datetime | None = None,
        paid_to: datetime | None = None,
        sort_by: AdminPaymentSortBy = AdminPaymentSortBy.PAID_AT,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> Page[AdminPaymentRead]:
        self._validate_payment_window(paid_from, paid_to)
        sort_column = {
            AdminPaymentSortBy.PAID_AT: StudentPayment.paid_at,
            AdminPaymentSortBy.AMOUNT_PAID: StudentPayment.amount_paid,
        }[sort_by]
        sort_expression = sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
        statement = self._apply_payment_filters(
            self._payment_ledger_statement().order_by(sort_expression, StudentPayment.id.asc()),
            q=q,
            payment_method=payment_method,
            package_id=package_id,
            currency=currency,
            paid_from=paid_from,
            paid_to=paid_to,
        )
        rows, total = await paginate_rows(self.session, statement, pagination)
        return Page(
            items=[
                self._payment_read(payment, student, user, package)
                for payment, student, user, package in rows
            ],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_payment(self, payment_id: UUID) -> AdminPaymentRead:
        result = await self.session.execute(
            self._payment_ledger_statement().where(StudentPayment.id == payment_id)
        )
        row = result.one_or_none()
        if row is None:
            raise NotFoundError("Student payment not found")
        return self._payment_read(*row)

    async def get_payment_summary(
        self,
        *,
        q: str | None = None,
        payment_method: PaymentMethod | None = None,
        package_id: UUID | None = None,
        currency: str | None = None,
        paid_from: datetime | None = None,
        paid_to: datetime | None = None,
    ) -> AdminPaymentSummaryRead:
        self._validate_payment_window(paid_from, paid_to)
        statement = (
            select(
                StudentPayment.currency,
                StudentPayment.payment_method,
                func.count(StudentPayment.id),
                func.coalesce(func.sum(StudentPayment.amount_paid), 0),
            )
            .join(Student, StudentPayment.student_id == Student.id)
            .join(User, Student.user_id == User.id)
            .group_by(StudentPayment.currency, StudentPayment.payment_method)
            .order_by(StudentPayment.currency.asc(), StudentPayment.payment_method.asc())
        )
        rows = (
            await self.session.execute(
                self._apply_payment_filters(
                    statement,
                    q=q,
                    payment_method=payment_method,
                    package_id=package_id,
                    currency=currency,
                    paid_from=paid_from,
                    paid_to=paid_to,
                )
            )
        ).all()
        grouped: dict[str, list[AdminPaymentMethodSummary]] = {}
        for row_currency, method, count, total in rows:
            grouped.setdefault(row_currency, []).append(
                AdminPaymentMethodSummary(
                    payment_method=method,
                    count=int(count),
                    total_amount_paid=int(total),
                )
            )
        summaries = []
        for row_currency, methods in grouped.items():
            count = sum(method.count for method in methods)
            total_amount_paid = sum(method.total_amount_paid for method in methods)
            summaries.append(
                AdminPaymentCurrencySummary(
                    currency=row_currency,
                    count=count,
                    total_amount_paid=total_amount_paid,
                    average_amount_paid=total_amount_paid // count if count else 0,
                    methods=methods,
                )
            )
        return AdminPaymentSummaryRead(currencies=summaries)

    async def create_payment(self, payment_in: AdminPaymentCreate) -> AdminPaymentRead:
        payment = await StudentPaymentService(self.session).create_payment(
            StudentPaymentCreate(**payment_in.model_dump())
        )
        return await self.get_payment(payment.id)

    async def update_payment(
        self,
        payment_id: UUID,
        payment_in: AdminStudentPaymentUpdate,
    ) -> AdminPaymentRead:
        await StudentPaymentService(self.session).update_payment(
            payment_id,
            StudentPaymentUpdate(**payment_in.model_dump(exclude_unset=True)),
        )
        return await self.get_payment(payment_id)

    async def delete_payment(self, payment_id: UUID) -> None:
        await StudentPaymentService(self.session).delete_payment(payment_id)

    def _payment_ledger_statement(self):
        return (
            select(StudentPayment, Student, User, Package)
            .join(Student, StudentPayment.student_id == Student.id)
            .join(User, Student.user_id == User.id)
            .outerjoin(Package, StudentPayment.package_id == Package.id)
        )

    def _apply_payment_filters(
        self,
        statement,
        *,
        q: str | None,
        payment_method: PaymentMethod | None,
        package_id: UUID | None,
        currency: str | None,
        paid_from: datetime | None,
        paid_to: datetime | None,
    ):
        normalized_q = _normalize_search_query(q)
        if normalized_q is not None:
            pattern = f"%{normalized_q}%"
            statement = statement.where(
                or_(
                    User.full_name.ilike(pattern),
                    User.email.ilike(pattern),
                    User.phone.ilike(pattern),
                )
            )
        if payment_method is not None:
            statement = statement.where(StudentPayment.payment_method == payment_method)
        if package_id is not None:
            statement = statement.where(StudentPayment.package_id == package_id)
        if currency is not None:
            statement = statement.where(StudentPayment.currency == currency.upper())
        if paid_from is not None:
            statement = statement.where(StudentPayment.paid_at >= paid_from)
        if paid_to is not None:
            statement = statement.where(StudentPayment.paid_at < paid_to)
        return statement

    def _payment_read(
        self,
        payment: StudentPayment,
        student: Student,
        user: User,
        package: Package | None,
    ) -> AdminPaymentRead:
        return AdminPaymentRead(
            **_model_values(payment),
            student=AdminPaymentStudentSummary(
                id=student.id,
                full_name=user.full_name,
                email=user.email,
                phone=user.phone,
            ),
            package=package,
        )

    def _validate_payment_window(
        self,
        paid_from: datetime | None,
        paid_to: datetime | None,
    ) -> None:
        if paid_from is not None and paid_to is not None and paid_from >= paid_to:
            raise ValueError("paid_from must be before paid_to")


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
