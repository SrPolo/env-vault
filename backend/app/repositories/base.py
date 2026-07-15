from typing import Generic, TypeVar
from uuid import UUID

from app.models.base import Base
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Base repository for standard CRUD operations.
    """

    model_class: type[ModelType]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, id: UUID | str) -> ModelType | None:
        """Fetch a record by its UUID."""
        query = select(self.model_class).where(getattr(self.model_class, "id") == id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    def add(self, obj: ModelType) -> ModelType:
        """
        Adds an object to the session.
        Requires the Unit of Work to commit() to persist it.
        """
        self.session.add(obj)
        return obj

    async def delete(self, id: UUID | str) -> None:
        """
        Hard deletes a record by ID.
        """
        query = delete(self.model_class).where(getattr(self.model_class, "id") == id)
        await self.session.execute(query)
