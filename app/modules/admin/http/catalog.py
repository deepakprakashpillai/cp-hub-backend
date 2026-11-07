from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.admin.http.types import (
    BatchGroupSortByQuery,
    IsActiveQuery,
    PackageSortByQuery,
    ReasonQuery,
    SearchQuery,
    SortOrderQuery,
)
from app.modules.admin.schemas import (
    AdminBatchGroupRead,
    AdminBatchGroupSortBy,
    AdminPackageSortBy,
    SortOrder,
)
from app.modules.batch_groups.schemas import (
    BatchGroupCreate,
    BatchGroupRead,
    BatchGroupUpdate,
    StudentBatchMembershipAssign,
    StudentBatchMembershipRead,
)
from app.modules.packages.schemas import PackageCreate, PackageRead, PackageUpdate
from app.modules.read_models.services import (
    AdminCatalogQueryService,
    AdminCatalogService,
)

router = APIRouter()


@router.get("/batch-groups", response_model=Page[AdminBatchGroupRead])
async def list_batch_groups(
    session: DBSession,
    pagination: Pagination,
    q: SearchQuery = None,
    is_active: IsActiveQuery = None,
    sort_by: BatchGroupSortByQuery = AdminBatchGroupSortBy.CREATED_AT,
    sort_order: SortOrderQuery = SortOrder.DESC,
) -> Page[AdminBatchGroupRead]:
    return await AdminCatalogQueryService(session).list_batch_groups(
        pagination,
        is_active=is_active,
        q=q,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.post(
    "/batch-groups",
    response_model=BatchGroupRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_batch_group(
    batch_group_in: BatchGroupCreate,
    session: DBSession,
) -> BatchGroupRead:
    return await AdminCatalogService(session).create_batch_group(batch_group_in)


@router.get("/batch-groups/{batch_group_id}", response_model=AdminBatchGroupRead)
async def get_batch_group(
    batch_group_id: UUID,
    session: DBSession,
) -> AdminBatchGroupRead:
    return await AdminCatalogService(session).get_batch_group(batch_group_id)


@router.patch("/batch-groups/{batch_group_id}", response_model=BatchGroupRead)
async def update_batch_group(
    batch_group_id: UUID,
    batch_group_in: BatchGroupUpdate,
    session: DBSession,
) -> BatchGroupRead:
    return await AdminCatalogService(session).update_batch_group(batch_group_id, batch_group_in)


@router.post("/batch-groups/{batch_group_id}/void", response_model=BatchGroupRead)
async def void_batch_group(
    batch_group_id: UUID,
    session: DBSession,
) -> BatchGroupRead:
    return await AdminCatalogService(session).void_batch_group(batch_group_id)


@router.get(
    "/batch-groups/{batch_group_id}/students",
    response_model=Page[StudentBatchMembershipRead],
)
async def list_batch_group_students(
    batch_group_id: UUID,
    session: DBSession,
    pagination: Pagination,
    is_active: IsActiveQuery = True,
) -> Page[StudentBatchMembershipRead]:
    return await AdminCatalogService(session).list_batch_group_students(
        batch_group_id=batch_group_id,
        pagination=pagination,
        is_active=is_active,
    )


@router.post(
    "/batch-groups/{batch_group_id}/students",
    response_model=StudentBatchMembershipRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_student_to_batch_group(
    batch_group_id: UUID,
    membership_in: StudentBatchMembershipAssign,
    session: DBSession,
) -> StudentBatchMembershipRead:
    return await AdminCatalogService(session).add_student_to_batch_group(
        batch_group_id,
        membership_in,
    )


@router.delete(
    "/batch-groups/{batch_group_id}/students/{student_id}",
    response_model=StudentBatchMembershipRead,
)
async def remove_student_from_batch_group(
    batch_group_id: UUID,
    student_id: UUID,
    session: DBSession,
    reason: ReasonQuery = None,
) -> StudentBatchMembershipRead:
    return await AdminCatalogService(session).remove_student_from_batch_group(
        batch_group_id,
        student_id,
        reason=reason,
    )


@router.get("/packages", response_model=Page[PackageRead])
async def list_packages(
    session: DBSession,
    pagination: Pagination,
    q: SearchQuery = None,
    is_active: IsActiveQuery = None,
    sort_by: PackageSortByQuery = AdminPackageSortBy.CREATED_AT,
    sort_order: SortOrderQuery = SortOrder.DESC,
) -> Page[PackageRead]:
    return await AdminCatalogService(session).list_packages(
        pagination,
        q=q,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.post("/packages", response_model=PackageRead, status_code=status.HTTP_201_CREATED)
async def create_package(
    package_in: PackageCreate,
    session: DBSession,
) -> PackageRead:
    return await AdminCatalogService(session).create_package(package_in)


@router.get("/packages/{package_id}", response_model=PackageRead)
async def get_package(
    package_id: UUID,
    session: DBSession,
) -> PackageRead:
    return await AdminCatalogService(session).get_package(package_id)


@router.patch("/packages/{package_id}", response_model=PackageRead)
async def update_package(
    package_id: UUID,
    package_in: PackageUpdate,
    session: DBSession,
) -> PackageRead:
    return await AdminCatalogService(session).update_package(package_id, package_in)


@router.post("/packages/{package_id}/void", response_model=PackageRead)
async def void_package(
    package_id: UUID,
    session: DBSession,
) -> PackageRead:
    return await AdminCatalogService(session).void_package(package_id)
