from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession
from app.modules.packages.schemas import PackageCreate, PackageRead, PackageUpdate
from app.modules.packages.service import PackageService

router = APIRouter()


@router.get("", response_model=list[PackageRead])
async def list_packages(session: DBSession) -> list[PackageRead]:
    return await PackageService(session).list_packages()


@router.post("", response_model=PackageRead, status_code=status.HTTP_201_CREATED)
async def create_package(
    package_in: PackageCreate,
    session: DBSession,
) -> PackageRead:
    return await PackageService(session).create_package(package_in)


@router.get("/{package_id}", response_model=PackageRead)
async def get_package(
    package_id: UUID,
    session: DBSession,
) -> PackageRead:
    return await PackageService(session).get_package(package_id)


@router.patch("/{package_id}", response_model=PackageRead)
async def update_package(
    package_id: UUID,
    package_in: PackageUpdate,
    session: DBSession,
) -> PackageRead:
    return await PackageService(session).update_package(package_id, package_in)
