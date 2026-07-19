from fastapi import APIRouter

from app.modules.bookings.routes import router as bookings_router
from app.modules.classes.routes import router as classes_router
from app.modules.leads.routes import router as leads_router
from app.modules.packages.routes import router as packages_router
from app.modules.schedules.routes import router as schedules_router
from app.modules.students.routes import router as students_router
from app.modules.teachers.routes import router as teachers_router
from app.modules.users.routes import router as users_router

api_router = APIRouter()

api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(students_router, prefix="/students", tags=["students"])
api_router.include_router(packages_router, prefix="/packages", tags=["packages"])
api_router.include_router(teachers_router, prefix="/teachers", tags=["teachers"])
api_router.include_router(schedules_router, prefix="/schedules", tags=["schedules"])
api_router.include_router(classes_router, prefix="/classes", tags=["classes"])
api_router.include_router(bookings_router, prefix="/bookings", tags=["bookings"])
api_router.include_router(leads_router, prefix="/leads", tags=["leads"])
