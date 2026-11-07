from fastapi import APIRouter

from app.modules.admin.http.accounts import router as accounts_router
from app.modules.admin.http.catalog import router as catalog_router
from app.modules.admin.http.classes import router as classes_router
from app.modules.admin.http.dashboard import router as dashboard_router
from app.modules.admin.http.finance import router as finance_router
from app.modules.admin.http.leads import router as leads_router
from app.modules.admin.http.scheduling import router as scheduling_router

router = APIRouter()
router.include_router(dashboard_router)
router.include_router(finance_router)
router.include_router(leads_router)
router.include_router(accounts_router)
router.include_router(scheduling_router)
router.include_router(catalog_router)
router.include_router(classes_router)
