from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.uow import AbstractUnitOfWork
from app.models.organization import Organization
from app.services.rbac import require_org_role


class OrganizationNotFoundError(Exception):
    pass


class OrganizationAlreadyExistsError(Exception):
    pass


class OrganizationService:
    """
    Organization lifecycle. Creation must go through create_organization_with_owner
    (SECURITY DEFINER) because ORM INSERT ... RETURNING is blocked by RLS until
    the owner membership exists.
    """

    async def create(
        self,
        uow: AbstractUnitOfWork,
        *,
        name: str,
        slug: str,
        user_id: UUID | str,
    ) -> Organization:
        existing = await uow.organizations.get_by_slug(slug)
        if existing is not None:
            raise OrganizationAlreadyExistsError(f"Organization slug '{slug}' is taken.")

        try:
            org = await uow.organizations.create_with_owner(name, slug, user_id)
            await uow.commit()
        except IntegrityError as exc:
            await uow.rollback()
            raise OrganizationAlreadyExistsError(
                f"Organization slug '{slug}' is taken."
            ) from exc
        return org

    async def get(
        self, uow: AbstractUnitOfWork, organization_id: UUID | str
    ) -> Organization:
        org = await uow.organizations.get(organization_id)
        if org is None:
            raise OrganizationNotFoundError("Organization not found.")
        return org

    async def list_for_user(self, uow: AbstractUnitOfWork) -> list[Organization]:
        """List orgs visible to the current RLS user (membership-based SELECT)."""
        return await uow.organizations.list_visible()

    async def update(
        self,
        uow: AbstractUnitOfWork,
        organization_id: UUID | str,
        *,
        actor_user_id: UUID | str,
        name: str | None = None,
        slug: str | None = None,
    ) -> Organization:
        await require_org_role(uow, organization_id, actor_user_id, "admin")
        org = await self.get(uow, organization_id)

        if slug is not None and slug != org.slug:
            conflict = await uow.organizations.get_by_slug(slug)
            if conflict is not None and conflict.id != org.id:
                raise OrganizationAlreadyExistsError(
                    f"Organization slug '{slug}' is taken."
                )
            org.slug = slug
        if name is not None:
            org.name = name

        try:
            await uow.commit()
        except IntegrityError as exc:
            await uow.rollback()
            raise OrganizationAlreadyExistsError(
                f"Organization slug '{slug}' is taken."
            ) from exc
        return org

    async def delete(
        self,
        uow: AbstractUnitOfWork,
        organization_id: UUID | str,
        *,
        actor_user_id: UUID | str,
    ) -> None:
        await require_org_role(uow, organization_id, actor_user_id, "owner")
        org = await self.get(uow, organization_id)
        await uow.organizations.delete(org.id)
        await uow.commit()


__all__ = [
    "OrganizationService",
    "OrganizationNotFoundError",
    "OrganizationAlreadyExistsError",
]
