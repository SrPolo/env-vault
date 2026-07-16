from __future__ import annotations

import typing

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker, set_rls_context
from app.repositories import (
    EncryptionKeyRepository,
    EnvironmentRepository,
    ProjectRepository,
    SecretRepository,
    SecretVersionRepository,
    UserRepository,
)


class AbstractUnitOfWork:
    """
    Abstract Base Class for the Unit of Work pattern.
    Provides the transactional boundary and exposes repositories.
    """
    
    users: UserRepository
    projects: ProjectRepository
    environments: EnvironmentRepository
    secrets: SecretRepository
    secret_versions: SecretVersionRepository
    encryption_keys: EncryptionKeyRepository

    async def __aenter__(self) -> AbstractUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: typing.Any,
        exc_val: typing.Any,
        traceback: typing.Any,
    ) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        raise NotImplementedError

    async def flush(self) -> None:
        raise NotImplementedError

    async def rollback(self) -> None:
        raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """
    SQLAlchemy specific implementation of the Unit of Work.
    Manages the AsyncSession lifecycle and injects it into repositories.
    Sets PostgreSQL row-level security (RLS) contexts for the transaction.
    """

    def __init__(
        self,
        user_id: str | None = None,
        org_id: str | None = None,
        session_factory=async_session_maker,
    ) -> None:
        self.user_id = user_id
        self.org_id = org_id
        self.session_factory = session_factory
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self.session_factory()
        
        # Seteamos el contexto RLS (local a la transacción)
        await set_rls_context(self.session, self.user_id, self.org_id)
        
        # Instantiate repositories with the current session
        self.users = UserRepository(self.session)
        self.projects = ProjectRepository(self.session)
        self.environments = EnvironmentRepository(self.session)
        self.secrets = SecretRepository(self.session)
        self.secret_versions = SecretVersionRepository(self.session)
        self.encryption_keys = EncryptionKeyRepository(self.session)
        
        return self

    async def __aexit__(
        self,
        exc_type: typing.Any,
        exc_val: typing.Any,
        traceback: typing.Any,
    ) -> None:
        await super().__aexit__(exc_type, exc_val, traceback)
        if self.session:
            await self.session.close()

    async def commit(self) -> None:
        if self.session:
            await self.session.commit()

    async def flush(self) -> None:
        if self.session:
            await self.session.flush()

    async def rollback(self) -> None:
        if self.session:
            await self.session.rollback()
