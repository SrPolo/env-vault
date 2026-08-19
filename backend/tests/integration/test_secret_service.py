import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.secret import Secret, SecretVersion
from app.models.user import User
from app.services.crypto import CryptoService
from app.services.membership import MembershipService
from app.services.environment import EnvironmentNotFoundError
from app.services.rbac import InsufficientRoleError, MembershipRequiredError
from app.services.secret import (
    EncryptionKeyNotFoundError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretService,
)
from tests.factories import TenantFixture, seed_tenant


@pytest.fixture
def secret_service(crypto_service: CryptoService) -> SecretService:
    return SecretService(crypto_service)


@pytest.fixture
def membership_service() -> MembershipService:
    return MembershipService()


async def _create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
) -> User:
    async with session_factory() as session:
        user = User(email=email, password_hash="not-a-real-hash", full_name="Test User")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_create_secret_persists_encrypted_value(
    uow_factory,
    tenant: TenantFixture,
    secret_service: SecretService,
) -> None:
    async with uow_factory() as uow:
        secret = await secret_service.create_secret(
            uow,
            tenant.environment_id,
            organization_id=tenant.org_id,
            key_name="DATABASE_URL",
            plain_value="postgres://user:pass@db/app",
            actor_user_id=tenant.user_id,
        )

    assert secret.id is not None
    assert secret.current_version_id is not None
    assert secret.key_name == "DATABASE_URL"

    async with uow_factory() as uow:
        stored = await uow.secrets.get(secret.id)
        version = await uow.secret_versions.get(secret.current_version_id)

    assert stored is not None
    assert version is not None
    assert version.version_number == 1
    assert version.encrypted_value != b"postgres://user:pass@db/app"
    assert b"postgres://user:pass@db/app" not in version.encrypted_value
    assert len(version.iv) == 12

    async with uow_factory() as uow:
        plain = await secret_service.get_decrypted_value(
            uow,
            secret.id,
            organization_id=tenant.org_id,
            actor_user_id=tenant.user_id,
        )
    assert plain == "postgres://user:pass@db/app"


@pytest.mark.asyncio
async def test_create_secret_rejects_duplicate_key_name(
    uow_factory,
    tenant: TenantFixture,
    secret_service: SecretService,
) -> None:
    async with uow_factory() as uow:
        await secret_service.create_secret(
            uow,
            tenant.environment_id,
            organization_id=tenant.org_id,
            key_name="API_KEY",
            plain_value="v1",
            actor_user_id=tenant.user_id,
        )

    async with uow_factory() as uow:
        with pytest.raises(SecretAlreadyExistsError):
            await secret_service.create_secret(
                uow,
                tenant.environment_id,
                organization_id=tenant.org_id,
                key_name="API_KEY",
                plain_value="v2",
                actor_user_id=tenant.user_id,
            )


@pytest.mark.asyncio
async def test_add_new_version_rotates_pointer(
    uow_factory,
    tenant: TenantFixture,
    secret_service: SecretService,
) -> None:
    async with uow_factory() as uow:
        secret = await secret_service.create_secret(
            uow,
            tenant.environment_id,
            organization_id=tenant.org_id,
            key_name="TOKEN",
            plain_value="version-1",
            actor_user_id=tenant.user_id,
        )
        first_version_id = secret.current_version_id

    async with uow_factory() as uow:
        new_version = await secret_service.add_new_version(
            uow,
            secret.id,
            organization_id=tenant.org_id,
            plain_value="version-2",
            actor_user_id=tenant.user_id,
        )

    assert new_version.version_number == 2
    assert new_version.id != first_version_id

    async with uow_factory() as uow:
        refreshed = await uow.secrets.get(secret.id)
        assert refreshed is not None
        assert refreshed.current_version_id == new_version.id
        assert (
            await secret_service.get_decrypted_value(
                uow,
                secret.id,
                organization_id=tenant.org_id,
                actor_user_id=tenant.user_id,
            )
            == "version-2"
        )

        # Previous version remains stored for history
        old = await uow.secret_versions.get(first_version_id)
        assert old is not None
        assert old.version_number == 1


@pytest.mark.asyncio
async def test_soft_delete_hides_secret_from_reads(
    uow_factory,
    tenant: TenantFixture,
    secret_service: SecretService,
) -> None:
    async with uow_factory() as uow:
        secret = await secret_service.create_secret(
            uow,
            tenant.environment_id,
            organization_id=tenant.org_id,
            key_name="TO_DELETE",
            plain_value="bye",
            actor_user_id=tenant.user_id,
        )

    async with uow_factory() as uow:
        await secret_service.delete_secret(
            uow,
            secret.id,
            organization_id=tenant.org_id,
            actor_user_id=tenant.user_id,
        )

    async with uow_factory() as uow:
        with pytest.raises(SecretNotFoundError):
            await secret_service.get_decrypted_value(
                uow,
                secret.id,
                organization_id=tenant.org_id,
                actor_user_id=tenant.user_id,
            )

        with pytest.raises(SecretNotFoundError):
            await secret_service.delete_secret(
                uow,
                secret.id,
                organization_id=tenant.org_id,
                actor_user_id=tenant.user_id,
            )

        # Soft-deleted row still exists, but lookup-by-name ignores it
        by_name = await uow.secrets.get_by_environment_and_name(
            tenant.environment_id, "TO_DELETE"
        )
        assert by_name is None

        stored = await uow.secrets.get(secret.id)
        assert stored is not None
        assert stored.is_deleted is True
        assert stored.deleted_at is not None


@pytest.mark.asyncio
async def test_create_secret_requires_active_encryption_key(
    uow_factory,
    tenant: TenantFixture,
    secret_service: SecretService,
) -> None:
    async with uow_factory() as uow:
        enc_key = await uow.encryption_keys.get(tenant.encryption_key_id)
        assert enc_key is not None
        enc_key.is_active = False
        await uow.commit()

    async with uow_factory() as uow:
        with pytest.raises(EncryptionKeyNotFoundError):
            await secret_service.create_secret(
                uow,
                tenant.environment_id,
                organization_id=tenant.org_id,
                key_name="NO_KEY",
                plain_value="x",
                actor_user_id=tenant.user_id,
            )


@pytest.mark.asyncio
async def test_plaintext_never_stored_in_secret_tables(
    uow_factory,
    tenant: TenantFixture,
    secret_service: SecretService,
) -> None:
    plain = "literally-this-exact-string-must-not-appear"

    async with uow_factory() as uow:
        secret = await secret_service.create_secret(
            uow,
            tenant.environment_id,
            organization_id=tenant.org_id,
            key_name="CHECK_PLAINTEXT",
            plain_value=plain,
            actor_user_id=tenant.user_id,
        )

    async with uow_factory() as uow:
        versions = (
            await uow.session.execute(
                select(SecretVersion).where(SecretVersion.secret_id == secret.id)
            )
        ).scalars().all()
        secrets = (
            await uow.session.execute(select(Secret).where(Secret.id == secret.id))
        ).scalars().all()

    needle = plain.encode("utf-8")
    for version in versions:
        assert needle not in version.encrypted_value
        assert needle not in version.iv
    for row in secrets:
        assert needle not in row.key_name.encode("utf-8")


@pytest.mark.asyncio
async def test_viewer_can_list_metadata_but_not_write_or_reveal(
    session_factory: async_sessionmaker[AsyncSession],
    uow_factory,
    tenant: TenantFixture,
    secret_service: SecretService,
    membership_service: MembershipService,
) -> None:
    viewer = await _create_user(session_factory, email="secret-viewer@example.com")

    async with uow_factory() as uow:
        await membership_service.invite(
            uow,
            tenant.org_id,
            email=viewer.email,
            role="viewer",
            actor_user_id=tenant.user_id,
        )

    async with uow_factory() as uow:
        secret = await secret_service.create_secret(
            uow,
            tenant.environment_id,
            organization_id=tenant.org_id,
            key_name="VIEWER_SCOPE",
            plain_value="top-secret",
            actor_user_id=tenant.user_id,
        )

    # Metadata is allowed for viewers.
    async with uow_factory(user_id=str(viewer.id)) as uow:
        listed = await secret_service.list_secrets(
            uow,
            tenant.environment_id,
            organization_id=tenant.org_id,
            actor_user_id=viewer.id,
        )
    assert [s.key_name for s in listed] == ["VIEWER_SCOPE"]

    # Reveal and every mutation are not.
    async with uow_factory(user_id=str(viewer.id)) as uow:
        with pytest.raises(InsufficientRoleError):
            await secret_service.get_decrypted_value(
                uow,
                secret.id,
                organization_id=tenant.org_id,
                actor_user_id=viewer.id,
            )

    async with uow_factory(user_id=str(viewer.id)) as uow:
        with pytest.raises(InsufficientRoleError):
            await secret_service.create_secret(
                uow,
                tenant.environment_id,
                organization_id=tenant.org_id,
                key_name="VIEWER_WRITE",
                plain_value="nope",
                actor_user_id=viewer.id,
            )

    async with uow_factory(user_id=str(viewer.id)) as uow:
        with pytest.raises(InsufficientRoleError):
            await secret_service.add_new_version(
                uow,
                secret.id,
                organization_id=tenant.org_id,
                plain_value="nope",
                actor_user_id=viewer.id,
            )

    async with uow_factory(user_id=str(viewer.id)) as uow:
        with pytest.raises(InsufficientRoleError):
            await secret_service.delete_secret(
                uow,
                secret.id,
                organization_id=tenant.org_id,
                actor_user_id=viewer.id,
            )


@pytest.mark.asyncio
async def test_non_member_cannot_touch_secrets(
    session_factory: async_sessionmaker[AsyncSession],
    uow_factory,
    tenant: TenantFixture,
    secret_service: SecretService,
) -> None:
    """A user with no membership in the org is rejected before any DB read."""
    outsider = await _create_user(session_factory, email="outsider@example.com")

    async with uow_factory(user_id=str(outsider.id)) as uow:
        with pytest.raises(MembershipRequiredError):
            await secret_service.list_secrets(
                uow,
                tenant.environment_id,
                organization_id=tenant.org_id,
                actor_user_id=outsider.id,
            )


@pytest.mark.asyncio
async def test_secret_of_another_org_is_not_reachable(
    session_factory: async_sessionmaker[AsyncSession],
    uow_factory,
    tenant: TenantFixture,
    crypto_service: CryptoService,
    secret_service: SecretService,
) -> None:
    """
    Passing a foreign environment id while authenticated in another org must fail
    even though the caller is a legitimate owner of their own org.
    """
    other = await seed_tenant(
        session_factory,
        crypto_service,
        email="other-secrets@example.com",
        org_name="Other Secrets Org",
        org_slug="other-secrets-org",
        project_name="Foreign",
        project_slug="foreign-secrets",
    )

    async with uow_factory() as uow:
        with pytest.raises(EnvironmentNotFoundError):
            await secret_service.create_secret(
                uow,
                other.environment_id,
                organization_id=tenant.org_id,
                key_name="CROSS_ORG",
                plain_value="nope",
                actor_user_id=tenant.user_id,
            )
