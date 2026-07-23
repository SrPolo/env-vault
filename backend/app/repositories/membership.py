from uuid import UUID

from sqlalchemy import func, select, update

from app.models.organization import Membership
from app.repositories.base import BaseRepository


class MembershipRepository(BaseRepository[Membership]):
    model_class = Membership

    async def get_by_user_and_org(
        self, user_id: UUID | str, organization_id: UUID | str
    ) -> Membership | None:
        query = select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_by_organization(
        self, organization_id: UUID | str
    ) -> list[Membership]:
        query = (
            select(Membership)
            .where(Membership.organization_id == organization_id)
            .order_by(Membership.created_at)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_by_user(self, user_id: UUID | str) -> list[Membership]:
        query = (
            select(Membership)
            .where(Membership.user_id == user_id)
            .order_by(Membership.created_at)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_owners(self, organization_id: UUID | str) -> int:
        query = (
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == organization_id,
                Membership.role == "owner",
            )
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def update_role(self, membership_id: UUID | str, role: str) -> bool:
        """Update role by id. Returns True if a row was affected under RLS."""
        result = await self.session.execute(
            update(Membership)
            .where(Membership.id == membership_id)
            .values(role=role)
        )
        return (result.rowcount or 0) > 0
