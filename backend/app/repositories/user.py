from sqlalchemy import select
from app.models.user import User
from app.repositories.base import BaseRepository

class UserRepository(BaseRepository[User]):
    model_class = User

    async def get_by_email(self, email: str) -> User | None:
        query = select(User).where(User.email == email)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
