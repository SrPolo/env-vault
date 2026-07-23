import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.uow import SqlAlchemyUnitOfWork
from app.models.project import Project
from app.services.crypto import CryptoService
from tests.factories import TenantFixture, seed_tenant


@pytest.mark.asyncio
async def test_uow_sets_rls_context_and_commits(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantFixture,
) -> None:
    async with SqlAlchemyUnitOfWork(
        user_id=str(tenant.user_id),
        org_id=str(tenant.org_id),
        session_factory=session_factory,
    ) as uow:
        assert uow.session is not None
        result = await uow.session.execute(
            text(
                "SELECT current_setting('app.current_user_id', true),"
                " current_setting('app.current_org_id', true)"
            )
        )
        user_ctx, org_ctx = result.one()
        assert user_ctx == str(tenant.user_id)
        assert org_ctx == str(tenant.org_id)

        project = await uow.projects.get(tenant.project_id)
        assert project is not None
        assert project.slug == "api"


@pytest.mark.asyncio
async def test_uow_rollbacks_on_exception(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantFixture,
) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with SqlAlchemyUnitOfWork(
            user_id=str(tenant.user_id),
            org_id=str(tenant.org_id),
            session_factory=session_factory,
        ) as uow:
            uow.projects.add(
                Project(
                    organization_id=tenant.org_id,
                    name="Temp",
                    slug="temp-rollback",
                    created_by=tenant.user_id,
                )
            )
            await uow.flush()
            raise RuntimeError("boom")

    async with SqlAlchemyUnitOfWork(
        user_id=str(tenant.user_id),
        org_id=str(tenant.org_id),
        session_factory=session_factory,
    ) as uow:
        result = await uow.session.execute(
            select(Project).where(Project.slug == "temp-rollback")
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_rls_hides_other_organization_projects(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantFixture,
    crypto_service: CryptoService,
) -> None:
    other = await seed_tenant(
        session_factory,
        crypto_service,
        email="other@example.com",
        org_name="Other Co",
        org_slug="other-co",
        project_name="Other API",
        project_slug="other-api",
    )

    async with SqlAlchemyUnitOfWork(
        user_id=str(tenant.user_id),
        org_id=str(tenant.org_id),
        session_factory=session_factory,
    ) as uow:
        own = await uow.projects.get(tenant.project_id)
        foreign = await uow.projects.get(other.project_id)
        assert own is not None
        assert foreign is None

    async with SqlAlchemyUnitOfWork(
        user_id=str(other.user_id),
        org_id=str(other.org_id),
        session_factory=session_factory,
    ) as uow:
        own = await uow.projects.get(other.project_id)
        foreign = await uow.projects.get(tenant.project_id)
        assert own is not None
        assert foreign is None


@pytest.mark.asyncio
async def test_rls_blocks_access_without_org_context(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantFixture,
) -> None:
    async with SqlAlchemyUnitOfWork(
        user_id=str(tenant.user_id),
        org_id=None,
        session_factory=session_factory,
    ) as uow:
        project = await uow.projects.get(tenant.project_id)
        assert project is None
