from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update

from app.models.user import RefreshToken, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model_class = User

    async def get_by_email(self, email: str) -> User | None:
        query = select(User).where(User.email == email)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """
    Persists refresh tokens by hash only; the raw token never touches the database.

    Reuse detection is scoped to the user: presenting an already-rotated token
    revokes every active token of that user. Coarser than per-family revocation,
    but it needs no extra column and logging out all devices is the desired
    outcome when a stolen token is replayed.
    """

    model_class = RefreshToken

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_active_for_user(self, user_id: UUID | str) -> list[RefreshToken]:
        query = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def revoke(self, token_id: UUID | str) -> None:
        query = (
            update(RefreshToken)
            .where(RefreshToken.id == token_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.session.execute(query)

    async def revoke_all_for_user(self, user_id: UUID | str) -> None:
        query = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.session.execute(query)
