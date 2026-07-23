from uuid import UUID

from sqlalchemy import select, text

from app.models.organization import Organization
from app.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    model_class = Organization

    async def get_by_slug(self, slug: str) -> Organization | None:
        query = select(Organization).where(Organization.slug == slug)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_visible(self) -> list[Organization]:
        """Return organizations visible under the current RLS context."""
        result = await self.session.execute(select(Organization).order_by(Organization.name))
        return list(result.scalars().all())

    async def create_with_owner(
        self, name: str, slug: str, user_id: UUID | str
    ) -> Organization:
        """
        Bootstrap an organization + owner membership via SECURITY DEFINER SQL.

        Direct ORM INSERT on organizations fails under FORCE RLS because
        INSERT ... RETURNING evaluates SELECT policies before membership exists.
        """
        row = (
            await self.session.execute(
                text(
                    "SELECT id FROM create_organization_with_owner("
                    ":name, :slug, :user_id)"
                ),
                {"name": name, "slug": slug, "user_id": user_id},
            )
        ).one()
        org = await self.get(row.id)
        if org is None:
            raise RuntimeError(
                "Organization created but not visible under RLS; "
                "ensure app.current_user_id matches the owner user_id."
            )
        return org
