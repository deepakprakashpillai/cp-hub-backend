from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.packages.models import Package
from app.modules.student_payments.models import StudentPayment
from app.modules.student_payments.schemas import StudentPaymentCreate, StudentPaymentUpdate
from app.modules.students.models import Student
from app.modules.users.models import User


class StudentPaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_payments(self, student_id: UUID | None = None) -> list[StudentPayment]:
        query = select(StudentPayment).order_by(StudentPayment.paid_at.desc())
        if student_id is not None:
            query = query.where(StudentPayment.student_id == student_id)

        result = await self.session.scalars(query)
        return list(result)

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

        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def delete_payment(self, payment_id: UUID) -> None:
        payment = await self.get_payment(payment_id)
        await self.session.delete(payment)
        await self.session.commit()

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
