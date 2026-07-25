from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import ConflictError
from app.modules.batch_groups.models import BatchGroup
from app.modules.batch_groups.schemas import (
    BatchGroupCreate,
    BatchGroupRead,
    StudentBatchMembershipAssign,
)
from app.modules.batch_groups.service import BatchGroupService
from app.modules.packages.models import Package
from app.modules.packages.service import PackageService


def test_batch_group_read_includes_compact_package() -> None:
    now = datetime.now(UTC)
    package_id = uuid4()
    read = BatchGroupRead.model_validate(
        {
            "id": uuid4(),
            "name": "Grade 8",
            "package_id": package_id,
            "package": {
                "id": package_id,
                "name": "Quarterly",
                "duration_days": 90,
                "price_amount": 12000,
                "currency": "INR",
                "is_active": True,
            },
            "default_capacity": 12,
            "is_active": True,
            "notes": None,
            "created_at": now,
            "updated_at": now,
        }
    )

    assert read.package is not None
    assert read.package.id == package_id
    assert read.package.duration_days == 90


def test_package_access_override_requires_reason() -> None:
    with pytest.raises(ValidationError, match="reason is required"):
        StudentBatchMembershipAssign(
            student_id=uuid4(),
            allow_package_access_override=True,
        )


@pytest.mark.asyncio
async def test_active_batch_group_rejects_inactive_package() -> None:
    package = Package(
        id=uuid4(),
        name="Old",
        duration_days=30,
        price_amount=1000,
        currency="INR",
        is_active=False,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        get=AsyncMock(return_value=package),
        commit=AsyncMock(),
    )

    with pytest.raises(ConflictError, match="active package"):
        await BatchGroupService(session).create_batch_group(
            BatchGroupCreate(
                name="Grade 8",
                package_id=package.id,
                default_capacity=12,
            )
        )

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_membership_requires_current_matching_package_grant() -> None:
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    service = BatchGroupService(session)
    batch_group = BatchGroup(
        id=uuid4(),
        name="Grade 8",
        package_id=uuid4(),
        default_capacity=12,
        is_active=True,
    )

    with pytest.raises(ConflictError, match="current access"):
        await service._validate_student_package_access(
            uuid4(),
            batch_group,
            allow_override=False,
        )


@pytest.mark.asyncio
async def test_reasoned_package_access_override_bypasses_grant_lookup() -> None:
    session = SimpleNamespace(scalar=AsyncMock())
    service = BatchGroupService(session)
    batch_group = BatchGroup(
        id=uuid4(),
        name="Legacy",
        package_id=None,
        default_capacity=12,
        is_active=True,
    )

    await service._validate_student_package_access(
        uuid4(),
        batch_group,
        allow_override=True,
    )

    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_void_package_rejects_active_batch_group_link() -> None:
    package = Package(
        id=uuid4(),
        name="Quarterly",
        duration_days=90,
        price_amount=12000,
        currency="INR",
        is_active=True,
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=package),
        scalar=AsyncMock(return_value=uuid4()),
        commit=AsyncMock(),
    )

    with pytest.raises(ConflictError, match="active batch group"):
        await PackageService(session).void_package(package.id)

    session.commit.assert_not_awaited()
