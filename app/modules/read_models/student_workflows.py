from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.pagination import Page, PaginationParams
from app.modules.batch_groups.models import StudentBatchMembership
from app.modules.batch_groups.schemas import (
    StudentBatchTransfer,
)
from app.modules.batch_groups.service import (
    BatchMembershipService,
)
from app.modules.read_models.admin_schemas import (
    AdminStudentAccessGrantCreate,
    AdminStudentAccessState,
    AdminStudentBatchGroupSet,
    AdminStudentPaymentCreate,
    AdminStudentPaymentUpdate,
)
from app.modules.student_access_grants.models import StudentAccessGrant
from app.modules.student_access_grants.schemas import StudentAccessGrantCreate
from app.modules.student_access_grants.service import StudentAccessGrantService
from app.modules.student_payments.models import StudentPayment
from app.modules.student_payments.schemas import StudentPaymentCreate, StudentPaymentUpdate
from app.modules.student_payments.service import StudentPaymentService
from app.modules.students.models import Student, StudentProgramChange
from app.modules.students.schemas import StudentProgramSwitch
from app.modules.students.workflows import StudentProgramWorkflow


class _ServiceBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class AdminStudentWorkflowService(_ServiceBase):
    async def list_student_payments(
        self,
        student_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        return await StudentPaymentService(self.session).list_payments(
            pagination,
            student_id=student_id,
        )

    async def create_student_payment(
        self,
        student_id: UUID,
        payment_in: AdminStudentPaymentCreate,
    ) -> StudentPayment:
        return await StudentPaymentService(self.session).create_payment(
            StudentPaymentCreate(
                student_id=student_id,
                package_id=payment_in.package_id,
                amount_paid=payment_in.amount_paid,
                currency=payment_in.currency,
                payment_method=payment_in.payment_method,
                paid_at=payment_in.paid_at,
                created_by_user_id=payment_in.created_by_user_id,
                notes=payment_in.notes,
            )
        )

    async def update_student_payment(
        self,
        student_id: UUID,
        payment_id: UUID,
        payment_in: AdminStudentPaymentUpdate,
    ) -> StudentPayment:
        payment_service = StudentPaymentService(self.session)
        payment = await payment_service.get_payment(payment_id)
        if payment.student_id != student_id:
            raise ConflictError("Payment does not belong to student")
        return await payment_service.update_payment(
            payment_id,
            StudentPaymentUpdate(**payment_in.model_dump(exclude_unset=True)),
        )

    async def delete_student_payment(self, student_id: UUID, payment_id: UUID) -> None:
        payment_service = StudentPaymentService(self.session)
        payment = await payment_service.get_payment(payment_id)
        if payment.student_id != student_id:
            raise ConflictError("Payment does not belong to student")
        await payment_service.delete_payment(payment_id)

    async def list_student_access_grants(
        self,
        student_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        return await StudentAccessGrantService(self.session).list_grants(
            pagination,
            student_id=student_id,
        )

    async def create_student_access_grant(
        self,
        student_id: UUID,
        grant_in: AdminStudentAccessGrantCreate,
    ) -> StudentAccessGrant:
        return await StudentAccessGrantService(self.session).create_grant(
            StudentAccessGrantCreate(
                student_id=student_id,
                package_id=grant_in.package_id,
                grant_type=grant_in.grant_type,
                duration_days=grant_in.duration_days,
                access_starts_at=grant_in.access_starts_at,
                extend_current_access=grant_in.extend_current_access,
                created_by_user_id=grant_in.created_by_user_id,
                notes=grant_in.notes,
            )
        )

    async def switch_student_program(
        self,
        student_id: UUID,
        switch_in: StudentProgramSwitch,
    ) -> StudentProgramChange:
        return await StudentProgramWorkflow(self.session).switch_program(student_id, switch_in)

    async def set_student_batch_group(
        self,
        student_id: UUID,
        batch_group_in: AdminStudentBatchGroupSet,
    ) -> StudentBatchMembership:
        return await BatchMembershipService(self.session).transfer_student_batch_group(
            student_id,
            StudentBatchTransfer(
                batch_group_id=batch_group_in.batch_group_id,
                assigned_by_user_id=batch_group_in.assigned_by_user_id,
                reason=batch_group_in.reason,
                allow_package_access_override=(batch_group_in.allow_package_access_override),
            ),
        )

    async def list_student_batch_memberships(
        self,
        student_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        return await BatchMembershipService(self.session).list_student_batch_memberships(
            student_id,
            pagination,
        )


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
