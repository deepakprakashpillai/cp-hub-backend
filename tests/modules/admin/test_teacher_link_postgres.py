"""PostgreSQL integration tests; set CP_HUB_TEST_DATABASE_URL to a disposable database."""

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.read_models.account_services import AdminAccountWorkflow
from app.modules.read_models.admin_schemas import AdminTeacherLinkRequest
from app.modules.teachers.models import Teacher
from app.modules.users.models import User
from app.shared.enums import UserRole

DB_URL = os.environ.get("CP_HUB_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DB_URL, reason="Set CP_HUB_TEST_DATABASE_URL for PostgreSQL tests"
)


@pytest_asyncio.fixture
async def database():
    schema = "onboarding_test_" + uuid4().hex
    admin_engine = create_async_engine(DB_URL)
    async with admin_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": f"{schema},public"}}
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(User.__table__.create)
            await conn.run_sync(Teacher.__table__.create)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


async def create_admin(factory):
    async with factory() as session:
        user = User(
            full_name="Admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            is_active=True,
            password_hash="keep",
        )
        session.add(user)
        await session.commit()
        return user.id


@pytest.mark.asyncio
async def test_concurrent_retries_create_one_profile_and_keep_account(database):
    user_id = await create_admin(database)

    async def link(name):
        async with database() as session:
            # This models self-linking, where authentication already loaded the same ORM instance.
            await session.get(User, user_id)
            return await AdminAccountWorkflow(session).link_existing_admin(
                AdminTeacherLinkRequest(user_id=user_id, display_name=name)
            )

    results = await asyncio.gather(link("First"), link("Second"))
    assert sorted(result.profile_already_existed for result in results) == [False, True]
    assert results[0].teacher.id == results[1].teacher.id
    assert results[0].teacher.display_name == results[1].teacher.display_name
    async with database() as session:
        user = await session.get(User, user_id)
        teachers = (await session.scalars(select(Teacher))).all()
        assert user.roles == [UserRole.ADMIN, UserRole.TEACHER]
        assert user.password_hash == "keep"
        assert len(teachers) == 1


@pytest.mark.asyncio
async def test_database_rollback_after_profile_creation_failure(database, monkeypatch):
    user_id = await create_admin(database)
    async with database() as session:

        async def fail():
            raise RuntimeError("profile failure")

        monkeypatch.setattr(session, "flush", fail)
        with pytest.raises(RuntimeError, match="profile failure"):
            await AdminAccountWorkflow(session).link_existing_admin(
                AdminTeacherLinkRequest(user_id=user_id, display_name="Teacher")
            )
    async with database() as session:
        user = await session.get(User, user_id)
        assert user.roles == [UserRole.ADMIN]
        assert (await session.scalars(select(Teacher))).all() == []
