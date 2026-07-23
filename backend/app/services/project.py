from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.uow import AbstractUnitOfWork
from app.models.project import Project
from app.services.rbac import InsufficientRoleError, require_org_role


class ProjectNotFoundError(Exception):
    pass


class ProjectAlreadyExistsError(Exception):
    pass


class ProjectService:
    """Project CRUD scoped to an organization. Viewers are read-only."""

    async def create(
        self,
        uow: AbstractUnitOfWork,
        organization_id: UUID | str,
        *,
        name: str,
        slug: str,
        actor_user_id: UUID | str,
        description: str | None = None,
    ) -> Project:
        await require_org_role(uow, organization_id, actor_user_id, "member")

        existing = await uow.projects.get_by_org_and_slug(organization_id, slug)
        if existing is not None:
            raise ProjectAlreadyExistsError(
                f"Project slug '{slug}' already exists in this organization."
            )

        project = Project(
            organization_id=organization_id,
            name=name,
            slug=slug,
            description=description,
            created_by=actor_user_id,
        )
        uow.projects.add(project)
        try:
            await uow.commit()
        except IntegrityError as exc:
            await uow.rollback()
            raise ProjectAlreadyExistsError(
                f"Project slug '{slug}' already exists in this organization."
            ) from exc
        return project

    async def list(
        self,
        uow: AbstractUnitOfWork,
        organization_id: UUID | str,
        *,
        actor_user_id: UUID | str,
    ) -> list[Project]:
        await require_org_role(uow, organization_id, actor_user_id, "viewer")
        return await uow.projects.list_by_organization(organization_id)

    async def get(
        self,
        uow: AbstractUnitOfWork,
        project_id: UUID | str,
        *,
        organization_id: UUID | str,
        actor_user_id: UUID | str,
    ) -> Project:
        await require_org_role(uow, organization_id, actor_user_id, "viewer")
        project = await uow.projects.get(project_id)
        if project is None or str(project.organization_id) != str(organization_id):
            raise ProjectNotFoundError("Project not found.")
        return project

    async def update(
        self,
        uow: AbstractUnitOfWork,
        project_id: UUID | str,
        *,
        organization_id: UUID | str,
        actor_user_id: UUID | str,
        name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
    ) -> Project:
        await require_org_role(uow, organization_id, actor_user_id, "member")
        project = await self.get(
            uow,
            project_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )

        if slug is not None and slug != project.slug:
            conflict = await uow.projects.get_by_org_and_slug(organization_id, slug)
            if conflict is not None and conflict.id != project.id:
                raise ProjectAlreadyExistsError(
                    f"Project slug '{slug}' already exists in this organization."
                )
            project.slug = slug
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description

        try:
            await uow.commit()
        except IntegrityError as exc:
            await uow.rollback()
            raise ProjectAlreadyExistsError(
                f"Project slug '{slug}' already exists in this organization."
            ) from exc
        return project

    async def delete(
        self,
        uow: AbstractUnitOfWork,
        project_id: UUID | str,
        *,
        organization_id: UUID | str,
        actor_user_id: UUID | str,
    ) -> None:
        await require_org_role(uow, organization_id, actor_user_id, "member")
        project = await self.get(
            uow,
            project_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        await uow.projects.delete(project.id)
        await uow.commit()


__all__ = [
    "ProjectService",
    "ProjectNotFoundError",
    "ProjectAlreadyExistsError",
    "InsufficientRoleError",
]
