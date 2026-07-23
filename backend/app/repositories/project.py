from uuid import UUID

from sqlalchemy import select

from app.models.project import Environment, Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model_class = Project

    async def list_by_organization(
        self, organization_id: UUID | str
    ) -> list[Project]:
        query = (
            select(Project)
            .where(Project.organization_id == organization_id)
            .order_by(Project.name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_org_and_slug(
        self, organization_id: UUID | str, slug: str
    ) -> Project | None:
        query = select(Project).where(
            Project.organization_id == organization_id,
            Project.slug == slug,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class EnvironmentRepository(BaseRepository[Environment]):
    model_class = Environment

    async def get_by_project(self, project_id: UUID | str) -> list[Environment]:
        query = (
            select(Environment)
            .where(Environment.project_id == project_id)
            .order_by(Environment.name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_project_and_name(
        self, project_id: UUID | str, name: str
    ) -> Environment | None:
        query = select(Environment).where(
            Environment.project_id == project_id,
            Environment.name == name,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
