import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.uow import SqlAlchemyUnitOfWork
from app.models.user import User
from app.services.crypto import CryptoService
from app.services.environment import EnvironmentService
from app.services.membership import (
    InsufficientRoleError,
    InvalidMembershipRoleError,
    LastOwnerError,
    MembershipService,
)
from app.services.organization import (
    OrganizationAlreadyExistsError,
    OrganizationService,
)
from app.services.project import ProjectService
from app.services.secret import SecretService
from tests.factories import TenantFixture, seed_tenant


@pytest.fixture
def organization_service() -> OrganizationService:
    return OrganizationService()


@pytest.fixture
def membership_service() -> MembershipService:
    return MembershipService()


@pytest.fixture
def project_service() -> ProjectService:
    return ProjectService()


@pytest.fixture
def environment_service(crypto_service: CryptoService) -> EnvironmentService:
    return EnvironmentService(crypto_service)


@pytest.fixture
def secret_service(crypto_service: CryptoService) -> SecretService:
    return SecretService(crypto_service)


async def _create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
    full_name: str = "Test User",
) -> User:
    async with session_factory() as session:
        user = User(email=email, password_hash="not-a-real-hash", full_name=full_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


def _uow(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id,
    org_id=None,
) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(
        user_id=str(user_id),
        org_id=str(org_id) if org_id is not None else None,
        session_factory=session_factory,
    )


@pytest.mark.asyncio
async def test_create_organization_with_owner_membership(
    session_factory: async_sessionmaker[AsyncSession],
    organization_service: OrganizationService,
) -> None:
    user = await _create_user(session_factory, email="founder@example.com")

    async with _uow(session_factory, user_id=user.id) as uow:
        org = await organization_service.create(
            uow, name="Foundry", slug="foundry", user_id=user.id
        )

    assert org.id is not None
    assert org.slug == "foundry"

    async with _uow(session_factory, user_id=user.id, org_id=org.id) as uow:
        membership = await uow.memberships.get_by_user_and_org(user.id, org.id)
        assert membership is not None
        assert membership.role == "owner"

        orgs = await organization_service.list_for_user(uow)
        assert any(o.id == org.id for o in orgs)


@pytest.mark.asyncio
async def test_create_organization_rejects_duplicate_slug(
    session_factory: async_sessionmaker[AsyncSession],
    organization_service: OrganizationService,
) -> None:
    user = await _create_user(session_factory, email="dup@example.com")

    async with _uow(session_factory, user_id=user.id) as uow:
        await organization_service.create(
            uow, name="One", slug="same-slug", user_id=user.id
        )

    other = await _create_user(session_factory, email="other-dup@example.com")
    async with _uow(session_factory, user_id=other.id) as uow:
        with pytest.raises(OrganizationAlreadyExistsError):
            await organization_service.create(
                uow, name="Two", slug="same-slug", user_id=other.id
            )


@pytest.mark.asyncio
async def test_create_project_and_environment_with_active_dek(
    session_factory: async_sessionmaker[AsyncSession],
    organization_service: OrganizationService,
    project_service: ProjectService,
    environment_service: EnvironmentService,
    secret_service: SecretService,
) -> None:
    user = await _create_user(session_factory, email="builder@example.com")

    async with _uow(session_factory, user_id=user.id) as uow:
        org = await organization_service.create(
            uow, name="Build Co", slug="build-co", user_id=user.id
        )

    async with _uow(session_factory, user_id=user.id, org_id=org.id) as uow:
        project = await project_service.create(
            uow,
            org.id,
            name="Backend",
            slug="backend",
            actor_user_id=user.id,
        )

    async with _uow(session_factory, user_id=user.id, org_id=org.id) as uow:
        environment = await environment_service.create(
            uow,
            project.id,
            organization_id=org.id,
            name="staging",
            actor_user_id=user.id,
        )

    async with _uow(session_factory, user_id=user.id, org_id=org.id) as uow:
        enc_key = await uow.encryption_keys.get_active_for_environment(environment.id)
        assert enc_key is not None
        assert enc_key.is_active is True
        assert enc_key.key_version == 1
        assert len(enc_key.wrapped_dek) > 0

    async with _uow(session_factory, user_id=user.id, org_id=org.id) as uow:
        secret = await secret_service.create_secret(
            uow,
            environment.id,
            organization_id=org.id,
            key_name="SMOKE_KEY",
            plain_value="smoke-value",
            actor_user_id=user.id,
        )

    async with _uow(session_factory, user_id=user.id, org_id=org.id) as uow:
        assert secret.current_version_id is not None
        assert (
            await secret_service.get_decrypted_value(
                uow,
                secret.id,
                organization_id=org.id,
                actor_user_id=user.id,
            )
            == "smoke-value"
        )


@pytest.mark.asyncio
async def test_membership_invite_and_role_rules(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantFixture,
    membership_service: MembershipService,
) -> None:
    invitee = await _create_user(session_factory, email="invitee@example.com")

    async with _uow(
        session_factory, user_id=tenant.user_id, org_id=tenant.org_id
    ) as uow:
        membership = await membership_service.invite(
            uow,
            tenant.org_id,
            email=invitee.email,
            role="member",
            actor_user_id=tenant.user_id,
        )
        assert membership.role == "member"
        assert membership.user_id == invitee.id

    # New UoW after commit: transaction-local RLS GUCs reset on commit.
    async with _uow(
        session_factory, user_id=tenant.user_id, org_id=tenant.org_id
    ) as uow:
        members = await membership_service.list(
            uow, tenant.org_id, actor_user_id=tenant.user_id
        )
        assert len(members) == 2

    async with _uow(
        session_factory, user_id=tenant.user_id, org_id=tenant.org_id
    ) as uow:
        await membership_service.update_role(
            uow,
            tenant.org_id,
            membership.id,
            new_role="viewer",
            actor_user_id=tenant.user_id,
        )

    async with _uow(
        session_factory, user_id=invitee.id, org_id=tenant.org_id
    ) as uow:
        with pytest.raises(InsufficientRoleError):
            await membership_service.invite(
                uow,
                tenant.org_id,
                email="someone@example.com",
                role="member",
                actor_user_id=invitee.id,
            )

    async with _uow(
        session_factory, user_id=tenant.user_id, org_id=tenant.org_id
    ) as uow:
        with pytest.raises(InvalidMembershipRoleError):
            await membership_service.invite(
                uow,
                tenant.org_id,
                email="nope@example.com",
                role="owner",
                actor_user_id=tenant.user_id,
            )


@pytest.mark.asyncio
async def test_cannot_demote_last_owner(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantFixture,
    membership_service: MembershipService,
) -> None:
    async with _uow(
        session_factory, user_id=tenant.user_id, org_id=tenant.org_id
    ) as uow:
        owner_membership = await uow.memberships.get_by_user_and_org(
            tenant.user_id, tenant.org_id
        )
        assert owner_membership is not None

        with pytest.raises(LastOwnerError):
            await membership_service.update_role(
                uow,
                tenant.org_id,
                owner_membership.id,
                new_role="admin",
                actor_user_id=tenant.user_id,
            )

        with pytest.raises(LastOwnerError):
            await membership_service.remove(
                uow,
                tenant.org_id,
                owner_membership.id,
                actor_user_id=tenant.user_id,
            )


@pytest.mark.asyncio
async def test_rls_hides_cross_org_projects_via_services(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantFixture,
    crypto_service: CryptoService,
    project_service: ProjectService,
) -> None:
    other = await seed_tenant(
        session_factory,
        crypto_service,
        email="cross-org@example.com",
        org_name="Other Org",
        org_slug="other-org-svc",
        project_name="Foreign",
        project_slug="foreign",
    )

    async with _uow(
        session_factory, user_id=tenant.user_id, org_id=tenant.org_id
    ) as uow:
        projects = await project_service.list(
            uow, tenant.org_id, actor_user_id=tenant.user_id
        )
        assert {p.id for p in projects} == {tenant.project_id}
        foreign = await uow.projects.get(other.project_id)
        assert foreign is None


@pytest.mark.asyncio
async def test_viewer_cannot_create_project(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantFixture,
    membership_service: MembershipService,
    project_service: ProjectService,
) -> None:
    viewer = await _create_user(session_factory, email="viewer@example.com")

    async with _uow(
        session_factory, user_id=tenant.user_id, org_id=tenant.org_id
    ) as uow:
        await membership_service.invite(
            uow,
            tenant.org_id,
            email=viewer.email,
            role="viewer",
            actor_user_id=tenant.user_id,
        )

    async with _uow(
        session_factory, user_id=viewer.id, org_id=tenant.org_id
    ) as uow:
        with pytest.raises(InsufficientRoleError):
            await project_service.create(
                uow,
                tenant.org_id,
                name="Nope",
                slug="nope",
                actor_user_id=viewer.id,
            )
