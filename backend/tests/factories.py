from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import set_rls_context
from app.models.project import Environment, Project
from app.models.secret import EncryptionKey
from app.models.user import User
from app.services.crypto import CryptoService


@dataclass(frozen=True, slots=True)
class TenantFixture:
    user_id: UUID
    org_id: UUID
    project_id: UUID
    environment_id: UUID
    encryption_key_id: UUID
    email: str
    org_slug: str


async def seed_tenant(
    session_factory: async_sessionmaker[AsyncSession],
    crypto_service: CryptoService,
    *,
    email: str = "owner@example.com",
    org_name: str = "Acme",
    org_slug: str = "acme",
    project_name: str = "API",
    project_slug: str = "api",
    environment_name: str = "development",
) -> TenantFixture:
    """
    Bootstraps a minimal tenant graph under real Postgres RLS.

    Organization creation goes through create_organization_with_owner because
    INSERT ... RETURNING on organizations is otherwise blocked by the SELECT
    policy (membership does not exist yet).
    """
    async with session_factory() as session:
        user = User(email=email, password_hash="not-a-real-hash", full_name="Test Owner")
        session.add(user)
        await session.flush()

        await set_rls_context(session, user_id=str(user.id))

        org_row = (
            await session.execute(
                text(
                    "SELECT id FROM create_organization_with_owner("
                    ":name, :slug, :user_id)"
                ),
                {"name": org_name, "slug": org_slug, "user_id": user.id},
            )
        ).one()
        org_id: UUID = org_row.id

        await set_rls_context(session, user_id=str(user.id), org_id=str(org_id))

        project = Project(
            organization_id=org_id,
            name=project_name,
            slug=project_slug,
            created_by=user.id,
        )
        session.add(project)
        await session.flush()

        environment = Environment(project_id=project.id, name=environment_name)
        session.add(environment)
        await session.flush()

        wrapped_dek = crypto_service.create_wrapped_dek()
        enc_key = EncryptionKey(
            environment_id=environment.id,
            wrapped_dek=wrapped_dek,
            key_version=1,
            algorithm="AES-256-GCM",
            is_active=True,
        )
        session.add(enc_key)
        await session.commit()

        return TenantFixture(
            user_id=user.id,
            org_id=org_id,
            project_id=project.id,
            environment_id=environment.id,
            encryption_key_id=enc_key.id,
            email=email,
            org_slug=org_slug,
        )
