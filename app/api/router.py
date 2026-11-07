from fastapi import APIRouter, Depends

from app.modules.admin.routes import router as admin_router
from app.modules.auth.dependencies import get_current_teacher, require_roles
from app.modules.auth.routes import router as auth_router
from app.modules.batch_groups.routes import router as batch_groups_router
from app.modules.booking_notes.routes import router as booking_notes_router
from app.modules.bookings.routes import router as bookings_router
from app.modules.classes.routes import router as classes_router
from app.modules.leads.routes import router as leads_router
from app.modules.notifications.routes import notify_hub_router
from app.modules.notifications.routes import router as notifications_router
from app.modules.packages.routes import router as packages_router
from app.modules.portal.routes import student_router, teacher_router
from app.modules.schedules.routes import router as schedules_router
from app.modules.student_access_grants.routes import router as student_access_grants_router
from app.modules.student_payments.routes import router as student_payments_router
from app.modules.students.routes import router as students_router
from app.modules.teachers.routes import router as teachers_router
from app.modules.users.routes import router as users_router
from app.shared.enums import UserRole

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(
    notifications_router,
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER, UserRole.STUDENT))],
)
api_router.include_router(notify_hub_router, prefix="/notifications", tags=["notifications"])

admin_only = [Depends(require_roles(UserRole.ADMIN))]
teacher_only = [Depends(get_current_teacher)]
lead_only = [Depends(require_roles(UserRole.ADMIN, UserRole.LEAD_MANAGER))]

api_router.include_router(admin_router, prefix="/admin", tags=["admin"], dependencies=admin_only)
api_router.include_router(
    booking_notes_router,
    prefix="/teacher",
    tags=["teacher-booking-notes"],
    dependencies=teacher_only,
)
api_router.include_router(
    teacher_router, prefix="/teacher", tags=["teacher-portal"], dependencies=teacher_only
)
api_router.include_router(
    student_router,
    prefix="/student",
    tags=["student-portal"],
    dependencies=[Depends(require_roles(UserRole.STUDENT))],
)
api_router.include_router(
    batch_groups_router, prefix="/batch-groups", tags=["batch-groups"], dependencies=admin_only
)
api_router.include_router(users_router, prefix="/users", tags=["users"], dependencies=admin_only)
api_router.include_router(
    students_router, prefix="/students", tags=["students"], dependencies=admin_only
)
api_router.include_router(
    packages_router, prefix="/packages", tags=["packages"], dependencies=admin_only
)
api_router.include_router(
    student_payments_router,
    prefix="/student-payments",
    tags=["student-payments"],
    dependencies=admin_only,
)
api_router.include_router(
    student_access_grants_router,
    prefix="/student-access-grants",
    tags=["student-access-grants"],
    dependencies=admin_only,
)
api_router.include_router(
    teachers_router, prefix="/teachers", tags=["teachers"], dependencies=admin_only
)
api_router.include_router(
    schedules_router, prefix="/schedules", tags=["schedules"], dependencies=admin_only
)
api_router.include_router(
    classes_router, prefix="/classes", tags=["classes"], dependencies=admin_only
)
api_router.include_router(
    bookings_router, prefix="/bookings", tags=["bookings"], dependencies=admin_only
)
api_router.include_router(leads_router, prefix="/leads", tags=["leads"], dependencies=lead_only)
