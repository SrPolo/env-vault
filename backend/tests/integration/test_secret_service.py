import pytest
from sqlalchemy import select

from app.models.secret import Secret, SecretVersion
from app.services.crypto import CryptoService
from app.services.secret import (
    EncryptionKeyNotFoundError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretService,
)
from tests.factories import TenantFixture


@pytest.fixture
def secret_service(crypto_service: CryptoService) -> SecretService:
    return SecretService(crypto_service)


@pytest.mark.asyncio
async def test_create_secret_persists_encrypted_value(
    uow_factory,
    tenant: TenantFixture,
    secret_service: SecretService,
) -> None:
    async with uow_factory() as uow:
        secret = await secret_service.create_secret(
            uow,
            environment_id=tenant.environment_id,
            key_name="DATABASE_URL",
            plain_value="postgres://user:pass@db/app",
            user_id=tenant.user_id,
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
        plain = await secret_service.get_decrypted_value(uow, secret.id)
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
            environment_id=tenant.environment_id,
            key_name="API_KEY",
            plain_value="v1",
            user_id=tenant.user_id,
        )

    async with uow_factory() as uow:
        with pytest.raises(SecretAlreadyExistsError):
            await secret_service.create_secret(
                uow,
                environment_id=tenant.environment_id,
                key_name="API_KEY",
                plain_value="v2",
                user_id=tenant.user_id,
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
            environment_id=tenant.environment_id,
            key_name="TOKEN",
            plain_value="version-1",
            user_id=tenant.user_id,
        )
        first_version_id = secret.current_version_id

    async with uow_factory() as uow:
        new_version = await secret_service.add_new_version(
            uow,
            secret_id=secret.id,
            plain_value="version-2",
            user_id=tenant.user_id,
        )

    assert new_version.version_number == 2
    assert new_version.id != first_version_id

    async with uow_factory() as uow:
        refreshed = await uow.secrets.get(secret.id)
        assert refreshed is not None
        assert refreshed.current_version_id == new_version.id
        assert await secret_service.get_decrypted_value(uow, secret.id) == "version-2"

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
            environment_id=tenant.environment_id,
            key_name="TO_DELETE",
            plain_value="bye",
            user_id=tenant.user_id,
        )

    async with uow_factory() as uow:
        await secret_service.delete_secret(uow, secret.id)

    async with uow_factory() as uow:
        with pytest.raises(SecretNotFoundError):
            await secret_service.get_decrypted_value(uow, secret.id)

        with pytest.raises(SecretNotFoundError):
            await secret_service.delete_secret(uow, secret.id)

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
                environment_id=tenant.environment_id,
                key_name="NO_KEY",
                plain_value="x",
                user_id=tenant.user_id,
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
            environment_id=tenant.environment_id,
            key_name="CHECK_PLAINTEXT",
            plain_value=plain,
            user_id=tenant.user_id,
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
