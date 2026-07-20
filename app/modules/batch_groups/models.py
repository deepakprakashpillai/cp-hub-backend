from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BatchGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "batch_groups"
    __table_args__ = (
        CheckConstraint(
            "default_capacity > 0",
            name="ck_batch_groups_default_capacity_positive",
        ),
        Index(
            "uq_active_batch_groups_name",
            "name",
            unique=True,
            postgresql_where=text("is_active is true"),
        ),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    default_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class StudentBatchMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_batch_memberships"
    __table_args__ = (
        CheckConstraint(
            """
            (is_active is true and ended_at is null)
            or
            (is_active is false and ended_at is not null)
            """,
            name="ck_student_batch_memberships_active_end_state",
        ),
        Index(
            "uq_active_student_batch_membership",
            "student_id",
            unique=True,
            postgresql_where=text("is_active is true"),
        ),
    )

    student_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("students.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    batch_group_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("batch_groups.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
