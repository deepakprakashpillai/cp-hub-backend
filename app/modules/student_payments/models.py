from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import PaymentMethod, enum_values


class StudentPayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_payments"

    student_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("students.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    package_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("packages.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    amount_paid: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(
            PaymentMethod,
            name="payment_method",
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
