from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.notifications.service import NotificationService
from app.modules.packages.models import Package
from app.modules.student_payments.models import StudentPayment
from app.modules.student_payments.schemas import StudentPaymentCreate, StudentPaymentUpdate
from app.modules.students.models import Student
from app.modules.users.models import User


class StudentPaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_payments(
        self,
        pagination: PaginationParams,
        student_id: UUID | None = None,
    ) -> Page:
        query = select(StudentPayment).order_by(StudentPayment.paid_at.desc())
        if student_id is not None:
            query = query.where(StudentPayment.student_id == student_id)

        return await paginate_scalars(self.session, query, pagination)

    async def get_payment(self, payment_id: UUID) -> StudentPayment:
        payment = await self.session.get(StudentPayment, payment_id)
        if payment is None:
            raise NotFoundError("Student payment not found")
        return payment

    async def create_payment(self, payment_in: StudentPaymentCreate) -> StudentPayment:
        await self._validate_references(
            student_id=payment_in.student_id,
            package_id=payment_in.package_id,
            created_by_user_id=payment_in.created_by_user_id,
        )

        payment = StudentPayment(**payment_in.model_dump())
        self.session.add(payment)
        await self.session.flush()
        await self._emit_payment_notification(payment, "recorded", "medium")
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def update_payment(
        self,
        payment_id: UUID,
        payment_in: StudentPaymentUpdate,
    ) -> StudentPayment:
        payment = await self.get_payment(payment_id)
        update_data = payment_in.model_dump(exclude_unset=True)

        for non_nullable_field in (
            "student_id",
            "amount_paid",
            "currency",
            "payment_method",
            "paid_at",
        ):
            if non_nullable_field in update_data and update_data[non_nullable_field] is None:
                raise BadRequestError(f"{non_nullable_field} cannot be null")

        await self._validate_references(
            student_id=update_data.get("student_id"),
            package_id=update_data.get("package_id"),
            created_by_user_id=update_data.get("created_by_user_id"),
        )

        for field, value in update_data.items():
            setattr(payment, field, value)

        await self._emit_payment_notification(payment, "updated", "medium")
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def delete_payment(self, payment_id: UUID) -> None:
        payment = await self.get_payment(payment_id)
        await self._emit_payment_notification(payment, "removed", "high")
        await self.session.delete(payment)
        await self.session.commit()

    async def _emit_payment_notification(
        self, payment: StudentPayment, action: str, priority: str
    ) -> None:
        student = await self.session.get(Student, payment.student_id)
        if student is None:
            return
        await NotificationService(self.session).emit_to_users(
            event_type=f"payment.{action}",
            aggregate_type="student_payment",
            aggregate_id=payment.id,
            dedupe_key=f"notification:payment:{action}:{payment.id}",
            recipient_user_ids=[student.user_id],
            title="Payment record updated",
            body=(
                "A payment record was removed."
                if action == "removed"
                else f"A payment record was {action}."
            ),
            category="payments",
            priority=priority,
            action_url="/student",
            data={
                "student_id": str(student.id),
                "payment_id": str(payment.id),
                "amount_minor": payment.amount_paid,
                "currency": payment.currency,
                "payment_method": payment.payment_method.value,
                "paid_at": payment.paid_at.isoformat(),
                "package_name": None,
            },
            actor_user_id=payment.created_by_user_id,
            include_admins=True,
        )

    async def _validate_references(
        self,
        *,
        student_id: UUID | None,
        package_id: UUID | None,
        created_by_user_id: UUID | None,
    ) -> None:
        if student_id is not None:
            student = await self.session.get(Student, student_id)
            if student is None:
                raise NotFoundError("Student not found")

        if package_id is not None:
            package = await self.session.get(Package, package_id)
            if package is None:
                raise NotFoundError("Package not found")

        if created_by_user_id is not None:
            user = await self.session.get(User, created_by_user_id)
            if user is None:
                raise NotFoundError("User not found")
