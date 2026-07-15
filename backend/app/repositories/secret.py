from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from app.models.secret import Secret, SecretVersion, EncryptionKey
from app.repositories.base import BaseRepository


class SecretRepository(BaseRepository[Secret]):
    model_class = Secret

    async def get_by_environment_and_name(
        self, environment_id: UUID | str, key_name: str
    ) -> Secret | None:
        """
        Fetches an active (non-deleted) secret by its environment and name.
        """
        query = select(Secret).where(
            Secret.environment_id == environment_id,
            Secret.key_name == key_name,
            Secret.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def soft_delete(self, id: UUID | str) -> None:
        """
        Soft deletes a secret by marking it as deleted and setting the deleted_at timestamp.
        """
        query = (
            update(Secret)
            .where(Secret.id == id)
            .values(is_deleted=True, deleted_at=datetime.now(timezone.utc))
        )
        await self.session.execute(query)


class SecretVersionRepository(BaseRepository[SecretVersion]):
    model_class = SecretVersion

    async def get_latest_for_secret(self, secret_id: UUID | str) -> SecretVersion | None:
        query = (
            select(SecretVersion)
            .where(SecretVersion.secret_id == secret_id)
            .order_by(SecretVersion.version_number.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class EncryptionKeyRepository(BaseRepository[EncryptionKey]):
    model_class = EncryptionKey

    async def get_active_for_environment(
        self, environment_id: UUID | str
    ) -> EncryptionKey | None:
        query = select(EncryptionKey).where(
            EncryptionKey.environment_id == environment_id,
            EncryptionKey.is_active.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
