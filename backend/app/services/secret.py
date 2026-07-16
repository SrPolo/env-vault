from uuid import UUID

from app.core.uow import AbstractUnitOfWork
from app.models.secret import Secret, SecretVersion
from app.services.crypto import CryptoService


class SecretNotFoundError(Exception):
    pass


class SecretAlreadyExistsError(Exception):
    pass


class EncryptionKeyNotFoundError(Exception):
    pass


class SecretService:
    """
    Orchestrates secret management: creation, updating (versioning), retrieval, and deletion.
    Works closely with CryptoService for encryption/decryption and AbstractUnitOfWork for persistence.
    """

    def __init__(self, crypto_service: CryptoService):
        self.crypto = crypto_service

    async def create_secret(
        self,
        uow: AbstractUnitOfWork,
        environment_id: UUID | str,
        key_name: str,
        plain_value: str,
        user_id: UUID | str | None = None,
    ) -> Secret:
        """
        Creates a new secret and its initial version securely.
        """
        # 1. Verify uniqueness
        existing = await uow.secrets.get_by_environment_and_name(environment_id, key_name)
        if existing:
            raise SecretAlreadyExistsError(f"Secret '{key_name}' already exists in this environment.")

        # 2. Get the active Data Encryption Key (DEK) for the environment
        enc_key = await uow.encryption_keys.get_active_for_environment(environment_id)
        if not enc_key:
            raise EncryptionKeyNotFoundError("No active encryption key found for this environment.")

        # 3. Encrypt the secret value in memory
        encrypted_value, iv = self.crypto.encrypt_secret(plain_value, enc_key.wrapped_dek)

        # 4. Create the parent Secret record
        secret = Secret(environment_id=environment_id, key_name=key_name)
        uow.secrets.add(secret)
        
        # Flush to DB to let PostgreSQL generate the UUID for `secret.id`
        await uow.flush()

        # 5. Create the first SecretVersion record
        version = SecretVersion(
            secret_id=secret.id,
            encryption_key_id=enc_key.id,
            encrypted_value=encrypted_value,
            iv=iv,
            version_number=1,
            created_by=user_id,
        )
        uow.secret_versions.add(version)
        
        # Flush again to get the `version.id`
        await uow.flush()

        # 6. Update the pointer to the current version
        secret.current_version_id = version.id
        
        # 7. Commit the transaction
        await uow.commit()
        return secret

    async def add_new_version(
        self,
        uow: AbstractUnitOfWork,
        secret_id: UUID | str,
        plain_value: str,
        user_id: UUID | str | None = None,
    ) -> SecretVersion:
        """
        Rotates/Updates a secret by creating a new version with the new encrypted value.
        """
        secret = await uow.secrets.get(secret_id)
        if not secret or secret.is_deleted:
            raise SecretNotFoundError("Secret not found or deleted.")

        enc_key = await uow.encryption_keys.get_active_for_environment(secret.environment_id)
        if not enc_key:
            raise EncryptionKeyNotFoundError("No active encryption key found for this environment.")

        # Encrypt new value
        encrypted_value, iv = self.crypto.encrypt_secret(plain_value, enc_key.wrapped_dek)

        # Get latest version number
        latest_version = await uow.secret_versions.get_latest_for_secret(secret.id)
        new_version_number = (latest_version.version_number + 1) if latest_version else 1

        version = SecretVersion(
            secret_id=secret.id,
            encryption_key_id=enc_key.id,
            encrypted_value=encrypted_value,
            iv=iv,
            version_number=new_version_number,
            created_by=user_id,
        )
        uow.secret_versions.add(version)
        await uow.flush()

        # Update pointer
        secret.current_version_id = version.id
        await uow.commit()
        
        return version

    async def get_decrypted_value(
        self, uow: AbstractUnitOfWork, secret_id: UUID | str
    ) -> str:
        """
        Fetches the current version of a secret and decrypts its value.
        """
        secret = await uow.secrets.get(secret_id)
        if not secret or secret.is_deleted:
            raise SecretNotFoundError("Secret not found.")

        if not secret.current_version_id:
            raise ValueError("Secret has no active versions.")

        version = await uow.secret_versions.get(secret.current_version_id)
        if not version:
            raise ValueError("Current version record is missing.")

        enc_key = await uow.encryption_keys.get(version.encryption_key_id)
        if not enc_key:
            raise EncryptionKeyNotFoundError("Encryption key for this version is missing.")

        # Decrypt in memory
        plain_value = self.crypto.decrypt_secret(
            version.encrypted_value, version.iv, enc_key.wrapped_dek
        )
        return plain_value

    async def delete_secret(self, uow: AbstractUnitOfWork, secret_id: UUID | str) -> None:
        """
        Soft deletes a secret.
        """
        secret = await uow.secrets.get(secret_id)
        if not secret or secret.is_deleted:
            raise SecretNotFoundError("Secret not found or already deleted.")
            
        await uow.secrets.soft_delete(secret.id)
        await uow.commit()
