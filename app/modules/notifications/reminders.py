from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bookings.models import Booking
from app.modules.classes.models import ClassSession
from app.modules.notifications.service import NotificationService
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.shared.enums import BookingStatus, ClassSessionStatus
from app.shared.utils import utc_now


async def emit_due_reminders(session: AsyncSession) -> int:
    """Emit idempotent time-based reminders; invoke once per minute from a scheduler."""
    now = utc_now()
    service = NotificationService(session)
    emitted = 0
    class_window_end = now + timedelta(hours=1, minutes=1)
    rows = await session.execute(
        select(Booking, Student, ClassSession)
        .join(Student, Student.id == Booking.student_id)
        .join(ClassSession, ClassSession.id == Booking.class_session_id)
        .where(
            Booking.status == BookingStatus.BOOKED,
            ClassSession.status == ClassSessionStatus.SCHEDULED,
            ClassSession.starts_at >= now + timedelta(hours=1),
            ClassSession.starts_at < class_window_end,
        )
    )
    for booking, student, class_session in rows.all():
        audiences = {"student": [student.user_id]}
        teacher_name = None
        if class_session.teacher_id:
            teacher = await session.get(Teacher, class_session.teacher_id)
            if teacher:
                audiences["teacher"] = [teacher.user_id]
                teacher_name = teacher.display_name
        await service.emit_to_audiences(
            event_type="class.reminder_1h",
            aggregate_type="class_session",
            aggregate_id=class_session.id,
            dedupe_key=f"notification:class-reminder:{booking.id}",
            audiences=audiences,
            category="classes",
            priority="high",
            data={
                "class_id": str(class_session.id),
                "booking_id": str(booking.id),
                "starts_at": class_session.starts_at.isoformat(),
                "ends_at": class_session.ends_at.isoformat(),
                "teacher_name": teacher_name,
            },
        )
        emitted += 1
    for days, priority in ((7, "medium"), (1, "high")):
        window_start = now + timedelta(days=days)
        window_end = window_start + timedelta(minutes=1)
        students = await session.scalars(
            select(Student).where(
                Student.access_ends_at >= window_start,
                Student.access_ends_at < window_end,
            )
        )
        for student in students:
            await service.emit_to_users(
                event_type=f"access.expiring_{days}d",
                aggregate_type="student",
                aggregate_id=student.id,
                dedupe_key=f"notification:access-expiring:{days}:{student.id}",
                recipient_user_ids=[student.user_id],
                title="Your course access is ending soon",
                body=f"Your access ends in {days} {'day' if days == 1 else 'days'}.",
                category="access",
                priority=priority,
                action_url="/student",
                include_admins=True,
            )
            emitted += 1
    expired_students = await session.scalars(
        select(Student).where(
            Student.access_ends_at >= now - timedelta(minutes=1),
            Student.access_ends_at < now,
        )
    )
    for student in expired_students:
        await service.emit_to_users(
            event_type="access.expired",
            aggregate_type="student",
            aggregate_id=student.id,
            dedupe_key=f"notification:access-expired:{student.id}",
            recipient_user_ids=[student.user_id],
            title="Your course access has expired",
            body="Your course access has ended. Contact CP Hub to continue learning.",
            category="access",
            priority="high",
            action_url="/student",
            include_admins=True,
        )
        emitted += 1
    await session.commit()
    return emitted
