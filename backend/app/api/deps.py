from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import async_session_maker
from app.core.security.tokens import decode_access_token
from app.core.uow import AbstractUnitOfWork, SqlAlchemyUnitOfWork
from app.models.user import User
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.crypto import CryptoService
from app.services.environment import EnvironmentService
from app.services.membership import MembershipService
from app.services.organization import OrganizationService
from app.services.project import ProjectService
from app.services.secret import SecretService
from app.core.security.kms.local import LocalKMSProvider
from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Overridable in tests so HTTP tests share the testcontainers engine."""
    return async_session_maker


SessionFactoryDep = Annotated[
    async_sessionmaker[AsyncSession], Depends(get_session_factory)
]


async def get_auth_uow(
    session_factory: SessionFactoryDep,
) -> AsyncIterator[AbstractUnitOfWork]:
    """UoW without RLS context — for register/login/refresh/logout."""
    uow = SqlAlchemyUnitOfWork(session_factory=session_factory)
    async with uow:
        yield uow


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    session_factory: SessionFactoryDep,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user_id = payload["sub"]
    async with SqlAlchemyUnitOfWork(
        user_id=user_id, session_factory=session_factory
    ) as uow:
        user = await uow.users.get(user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_user_uow(
    current_user: CurrentUser,
    session_factory: SessionFactoryDep,
) -> AsyncIterator[AbstractUnitOfWork]:
    """UoW with user_id only — create/list organizations (no org context yet)."""
    uow = SqlAlchemyUnitOfWork(
        user_id=str(current_user.id),
        session_factory=session_factory,
    )
    async with uow:
        yield uow


async def get_org_uow(
    org_id: UUID,
    current_user: CurrentUser,
    session_factory: SessionFactoryDep,
) -> AsyncIterator[AbstractUnitOfWork]:
    """
    UoW scoped to org_id with membership gate.

    Path parameter must be named ``org_id`` so FastAPI injects it here.
    """
    uow = SqlAlchemyUnitOfWork(
        user_id=str(current_user.id),
        org_id=str(org_id),
        session_factory=session_factory,
    )
    async with uow:
        membership = await uow.memberships.get_by_user_and_org(
            current_user.id, org_id
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this organization",
            )
        yield uow


AuthUoW = Annotated[AbstractUnitOfWork, Depends(get_auth_uow)]
UserUoW = Annotated[AbstractUnitOfWork, Depends(get_user_uow)]
OrgUoW = Annotated[AbstractUnitOfWork, Depends(get_org_uow)]


def get_auth_service() -> AuthService:
    return AuthService()


def get_audit_service() -> AuditService:
    return AuditService()


def get_organization_service() -> OrganizationService:
    return OrganizationService()


def get_membership_service() -> MembershipService:
    return MembershipService()


def get_project_service() -> ProjectService:
    return ProjectService()


def get_crypto_service() -> CryptoService:
    return CryptoService(LocalKMSProvider(settings.ENCRYPTION_MASTER_KEY))


def get_environment_service(
    crypto: Annotated[CryptoService, Depends(get_crypto_service)],
) -> EnvironmentService:
    return EnvironmentService(crypto)


def get_secret_service(
    crypto: Annotated[CryptoService, Depends(get_crypto_service)],
) -> SecretService:
    return SecretService(crypto)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
OrganizationServiceDep = Annotated[
    OrganizationService, Depends(get_organization_service)
]
MembershipServiceDep = Annotated[MembershipService, Depends(get_membership_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
EnvironmentServiceDep = Annotated[
    EnvironmentService, Depends(get_environment_service)
]
SecretServiceDep = Annotated[SecretService, Depends(get_secret_service)]
