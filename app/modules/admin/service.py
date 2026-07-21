from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.schemas import (
    AdminStudentAccessGrantCreate,
    AdminStudentBatchGroupSet,
    AdminStudentCreate,
    AdminStudentPaymentCreate,
    AdminTeacherCreate,
)
from app.modules.batch_groups.models import StudentBatchMembership
from app.modules.batch_groups.schemas import BatchSessionBulkGenerate, StudentBatchTransfer
from app.modules.batch_groups.service import BatchGroupService
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    AdminAddStudentToClass,
    BatchBookingReschedule,
    BookingActionRequest,
    ClassAttendanceMark,
    OneOnOneBookingReschedule,
)
from app.modules.bookings.service import BookingService
from app.modules.classes.models import ClassSession
from app.modules.classes.schemas import BatchClassSessionCreate
from app.modules.classes.service import ClassSessionService
from app.modules.student_access_grants.models import StudentAccessGrant
from app.modules.student_access_grants.schemas import StudentAccessGrantCreate
from app.modules.student_access_grants.service import StudentAccessGrantService
from app.modules.student_payments.models import StudentPayment
from app.modules.student_payments.schemas import StudentPaymentCreate
from app.modules.student_payments.service import StudentPaymentService
from app.modules.students.models import Student, StudentProgramChange
from app.modules.students.schemas import StudentCreate, StudentProgramSwitch
from app.modules.students.service import StudentService
from app.modules.teachers.models import Teacher
from app.modules.teachers.schemas import TeacherCreate
from app.modules.teachers.service import TeacherService
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService
from app.shared.enums import UserRole


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_teacher(self, teacher_in: AdminTeacherCreate) -> tuple[User, Teacher]:
        user = await UserService(self.session).create_user(
            UserCreate(
                full_name=teacher_in.full_name,
                email=teacher_in.email,
                phone=teacher_in.phone,
                role=UserRole.TEACHER,
                is_active=teacher_in.is_active,
            ),
            commit=False,
        )
        teacher = await TeacherService(self.session).create_teacher(
            TeacherCreate(
                user_id=user.id,
                display_name=teacher_in.display_name,
                bio=teacher_in.bio,
                profile_photo_url=teacher_in.profile_photo_url,
            ),
            commit=False,
        )

        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(teacher)
        return user, teacher

    async def create_student(self, student_in: AdminStudentCreate) -> tuple[User, Student]:
        user = await UserService(self.session).create_user(
            UserCreate(
                full_name=student_in.full_name,
                email=student_in.email,
                phone=student_in.phone,
                role=UserRole.STUDENT,
                is_active=student_in.is_active,
            ),
            commit=False,
        )
        student = await StudentService(self.session).create_student(
            StudentCreate(
                user_id=user.id,
                program_type=student_in.program_type,
                status=student_in.status,
                access_starts_at=student_in.access_starts_at,
                access_ends_at=student_in.access_ends_at,
                notes=student_in.notes,
            ),
            commit=False,
        )

        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(student)
        return user, student

    async def list_student_payments(self, student_id: UUID) -> list[StudentPayment]:
        return await StudentPaymentService(self.session).list_payments(student_id=student_id)

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

    async def list_student_access_grants(self, student_id: UUID) -> list[StudentAccessGrant]:
        return await StudentAccessGrantService(self.session).list_grants(student_id=student_id)

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
        return await StudentService(self.session).switch_program(student_id, switch_in)

    async def set_student_batch_group(
        self,
        student_id: UUID,
        batch_group_in: AdminStudentBatchGroupSet,
    ) -> StudentBatchMembership:
        return await BatchGroupService(self.session).transfer_student_batch_group(
            student_id,
            StudentBatchTransfer(
                batch_group_id=batch_group_in.batch_group_id,
                assigned_by_user_id=batch_group_in.assigned_by_user_id,
                reason=batch_group_in.reason,
            ),
        )

    async def list_student_batch_memberships(
        self,
        student_id: UUID,
    ) -> list[StudentBatchMembership]:
        return await BatchGroupService(self.session).list_student_batch_memberships(student_id)

    async def generate_batch_sessions(
        self,
        batch_group_id: UUID,
        generation_in: BatchSessionBulkGenerate,
    ) -> list[ClassSession]:
        return await BatchGroupService(self.session).generate_batch_sessions(
            batch_group_id,
            generation_in,
        )

    async def create_batch_class_session(
        self,
        class_session_in: BatchClassSessionCreate,
    ) -> ClassSession:
        return await ClassSessionService(self.session).create_batch_class_session(class_session_in)

    async def add_student_to_class(
        self,
        class_session_id: UUID,
        add_in: AdminAddStudentToClass,
    ) -> Booking:
        return await BookingService(self.session).admin_add_student_to_class(
            class_session_id,
            add_in,
        )

    async def mark_class_attendance(
        self,
        class_session_id: UUID,
        attendance_in: ClassAttendanceMark,
    ) -> list[Booking]:
        return await BookingService(self.session).mark_class_attendance(
            class_session_id,
            attendance_in,
        )

    async def cancel_booking(
        self,
        booking_id: UUID,
        cancel_in: BookingActionRequest,
    ) -> Booking:
        return await BookingService(self.session).admin_cancel_booking(booking_id, cancel_in)

    async def reschedule_one_on_one_booking(
        self,
        booking_id: UUID,
        reschedule_in: OneOnOneBookingReschedule,
    ) -> Booking:
        return await BookingService(self.session).admin_reschedule_one_on_one_booking(
            booking_id,
            reschedule_in,
        )

    async def reschedule_batch_booking(
        self,
        booking_id: UUID,
        reschedule_in: BatchBookingReschedule,
    ) -> Booking:
        return await BookingService(self.session).admin_reschedule_batch_booking(
            booking_id,
            reschedule_in,
        )
