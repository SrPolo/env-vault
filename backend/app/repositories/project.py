from uuid import UUID
from sqlalchemy import select
from app.models.project import Project, Environment
from app.repositories.base import BaseRepository

class ProjectRepository(BaseRepository[Project]):
    model_class = Project


class EnvironmentRepository(BaseRepository[Environment]):
    model_class = Environment

    async def get_by_project(self, project_id: UUID | str) -> list[Environment]:
        query = select(Environment).where(Environment.project_id == project_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())
