from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate_scalars
from app.modules.batch_groups._shared import _BatchGroupShared
from app.modules.batch_groups.lifecycle_service import BatchGroupLifecycleService
from app.modules.batch_groups.models import StudentBatchMembership
from app.modules.batch_groups.schemas import (
    StudentBatchMembershipAssign,
    StudentBatchTransfer,
)
from app.modules.bookings.models import Booking, BookingEvent
from app.modules.classes.models import ClassSession
from app.modules.students.models import Student
from app.shared.enums import (
    BookingEventType,
    BookingStatus,
    DayOfWeek,
)
from app.shared.utils import utc_now

DAY_TO_INDEX = {
    DayOfWeek.MONDAY: 0,
    DayOfWeek.TUESDAY: 1,
    DayOfWeek.WEDNESDAY: 2,
    DayOfWeek.THURSDAY: 3,
    DayOfWeek.FRIDAY: 4,
    DayOfWeek.SATURDAY: 5,
    DayOfWeek.SUNDAY: 6,
}


class BatchMembershipService(_BatchGroupShared):
    async def list_batch_group_students(
        self,
        batch_group_id: UUID,
        pagination: PaginationParams,
        is_active: bool | None = True,
    ) -> Page:
        await BatchGroupLifecycleService(self.session).get_batch_group(batch_group_id)
        statement = (
            select(StudentBatchMembership)
            .where(StudentBatchMembership.batch_group_id == batch_group_id)
            .order_by(StudentBatchMembership.created_at.desc())
        )
        if is_active is not None:
            statement = statement.where(StudentBatchMembership.is_active.is_(is_active))

        return await paginate_scalars(self.session, statement, pagination)

    async def assign_student_to_batch_group(
        self,
        batch_group_id: UUID,
        membership_in: StudentBatchMembershipAssign,
    ) -> StudentBatchMembership:
        batch_group = await BatchGroupLifecycleService(self.session).get_batch_group(batch_group_id)
        if not batch_group.is_active:
            raise ConflictError("Cannot assign students to an inactive batch group")

        student = await self._get_batch_student(membership_in.student_id)
        await self._get_optional_user(membership_in.assigned_by_user_id)
        await self._validate_student_package_access(
            student.id,
            batch_group,
            allow_override=membership_in.allow_package_access_override,
        )

        active_membership = await self.get_active_student_membership(student.id)
        if active_membership is not None:
            if active_membership.batch_group_id == batch_group.id:
                raise ConflictError("Student is already active in this batch group")
            raise ConflictError("Student already has an active batch membership")

        membership = StudentBatchMembership(
            student_id=student.id,
            batch_group_id=batch_group.id,
            is_active=True,
            assigned_by_user_id=membership_in.assigned_by_user_id,
            assigned_at=utc_now(),
            end_reason=None,
        )
        self.session.add(membership)
        await self.session.commit()
        await self.session.refresh(membership)
        return membership

    async def transfer_student_batch_group(
        self,
        student_id: UUID,
        transfer_in: StudentBatchTransfer,
    ) -> StudentBatchMembership:
        student = await self._get_batch_student(student_id)
        batch_group = await BatchGroupLifecycleService(self.session).get_batch_group(
            transfer_in.batch_group_id
        )
        if not batch_group.is_active:
            raise ConflictError("Cannot transfer student to an inactive batch group")
        await self._get_optional_user(transfer_in.assigned_by_user_id)
        await self._validate_student_package_access(
            student.id,
            batch_group,
            allow_override=transfer_in.allow_package_access_override,
        )

        active_membership = await self.get_active_student_membership(student.id)
        if active_membership is not None and active_membership.batch_group_id == batch_group.id:
            raise ConflictError("Student is already active in this batch group")

        now = utc_now()
        if active_membership is not None:
            active_membership.is_active = False
            active_membership.ended_at = now
            active_membership.end_reason = transfer_in.reason
            await self._cancel_future_student_bookings_for_batch_group(
                student_id=student.id,
                batch_group_id=active_membership.batch_group_id,
                now=now,
            )

        membership = StudentBatchMembership(
            student_id=student.id,
            batch_group_id=batch_group.id,
            is_active=True,
            assigned_by_user_id=transfer_in.assigned_by_user_id,
            assigned_at=now,
            end_reason=None,
        )
        self.session.add(membership)
        await self.session.commit()
        await self.session.refresh(membership)
        return membership

    async def list_student_batch_memberships(
        self,
        student_id: UUID,
        pagination: PaginationParams,
    ) -> Page:
        student = await self.session.get(Student, student_id)
        if student is None:
            raise NotFoundError("Student not found")

        statement = (
            select(StudentBatchMembership)
            .where(StudentBatchMembership.student_id == student_id)
            .order_by(StudentBatchMembership.assigned_at.desc())
        )
        return await paginate_scalars(self.session, statement, pagination)

    async def get_active_student_membership(
        self,
        student_id: UUID,
    ) -> StudentBatchMembership | None:
        return await self.session.scalar(
            select(StudentBatchMembership).where(
                StudentBatchMembership.student_id == student_id,
                StudentBatchMembership.is_active.is_(True),
            )
        )

    async def end_active_student_membership(
        self,
        student_id: UUID,
        *,
        reason: str | None,
        now: datetime | None = None,
        commit: bool = True,
    ) -> bool:
        active_membership = await self.get_active_student_membership(student_id)
        if active_membership is None:
            return False

        ended_at = now or utc_now()
        active_membership.is_active = False
        active_membership.ended_at = ended_at
        active_membership.end_reason = reason

        if commit:
            await self.session.commit()

        return True

    async def remove_student_from_batch_group(
        self,
        batch_group_id: UUID,
        student_id: UUID,
        *,
        reason: str | None,
    ) -> StudentBatchMembership:
        await BatchGroupLifecycleService(self.session).get_batch_group(batch_group_id)
        student = await self.session.get(Student, student_id)
        if student is None:
            raise NotFoundError("Student not found")

        membership = await self.session.scalar(
            select(StudentBatchMembership)
            .where(
                StudentBatchMembership.batch_group_id == batch_group_id,
                StudentBatchMembership.student_id == student_id,
                StudentBatchMembership.is_active.is_(True),
            )
            .with_for_update()
        )
        if membership is None:
            raise NotFoundError("Active batch membership not found")

        now = utc_now()
        cancellation_reason = reason or "removed from batch group"
        membership.is_active = False
        membership.ended_at = now
        membership.end_reason = reason

        bookings = await self.session.scalars(
            select(Booking)
            .join(ClassSession, Booking.class_session_id == ClassSession.id)
            .where(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.BOOKED,
                ClassSession.batch_group_id == batch_group_id,
                ClassSession.starts_at > now,
            )
            .with_for_update()
        )
        for booking in bookings:
            booking.status = BookingStatus.CANCELLED
            self.session.add(
                BookingEvent(
                    booking_id=booking.id,
                    event_type=BookingEventType.CANCELLED_BY_ADMIN,
                    actor_user_id=None,
                    reason=cancellation_reason,
                    event_metadata={
                        "batch_group_id": str(batch_group_id),
                        "membership_id": str(membership.id),
                    },
                )
            )

        await self.session.commit()
        await self.session.refresh(membership)
        return membership
