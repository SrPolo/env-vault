from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from app.core.security.kms.local import LocalKMSProvider
from app.core.uow import SqlAlchemyUnitOfWork
from app.services.crypto import CryptoService
from tests.factories import TenantFixture, seed_tenant

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Non-superuser role used by the app under test. Superusers bypass RLS even with
# FORCE ROW LEVEL SECURITY, so tests must connect as a restricted role.
APP_DB_USER = "envvault_app"
APP_DB_PASSWORD = "envvault_app_password"

TABLES_TO_TRUNCATE = (
    "audit_logs",
    "secret_versions",
    "secrets",
    "encryption_keys",
    "api_tokens",
    "environments",
    "projects",
    "memberships",
    "organizations",
    "refresh_tokens",
    "users",
)


def _to_asyncpg_url(sync_url: str) -> str:
    """Convert a sync SQLAlchemy URL to asyncpg."""
    if sync_url.startswith("postgresql+psycopg2://"):
        return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if sync_url.startswith("postgresql+psycopg://"):
        return sync_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if sync_url.startswith("postgresql://"):
        return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return sync_url


def _replace_url_credentials(url: str, username: str, password: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    netloc = f"{quote(username)}:{quote(password)}@{host}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def _ensure_app_role_exists(admin_database_url: str) -> None:
    """
    Create envvault_app before Alembic runs.

    Mirrors backend/scripts/provision_app_role.sh (without --grants): migrations
    GRANT to this role and must not CREATE ROLE themselves (no CREATEROLE needed
    on the migration runner).
    """
    from sqlalchemy import create_engine

    # asyncpg URL → sync driver for a one-shot bootstrap outside the event loop
    sync_url = admin_database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    engine = create_engine(sync_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_roles WHERE rolname = '{APP_DB_USER}'
                        ) THEN
                            CREATE ROLE {APP_DB_USER} LOGIN PASSWORD '{APP_DB_PASSWORD}'
                                NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
                        ELSE
                            ALTER ROLE {APP_DB_USER} WITH LOGIN PASSWORD '{APP_DB_PASSWORD}'
                                NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
                        END IF;
                    END
                    $$;
                    """
                )
            )
    finally:
        engine.dispose()


def _run_migrations(database_url: str) -> None:
    # Must run outside an active event loop: alembic/env.py uses asyncio.run().
    os.environ["ENVVAULT_DATABASE_URL"] = database_url
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")


async def _grant_app_role_privileges(
    admin_engine: AsyncEngine, database_name: str
) -> None:
    """Grant DML privileges after migrations created tables/functions."""
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"GRANT CONNECT ON DATABASE {database_name} TO {APP_DB_USER}"))
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_DB_USER}"))
        await conn.execute(
            text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                f"IN SCHEMA public TO {APP_DB_USER}"
            )
        )
        await conn.execute(
            text(
                f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_DB_USER}"
            )
        )
        await conn.execute(
            text(
                f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {APP_DB_USER}"
            )
        )
        await conn.execute(
            text(
                "REVOKE ALL ON FUNCTION create_organization_with_owner(text, text, uuid) "
                "FROM PUBLIC"
            )
        )
        await conn.execute(
            text(
                f"GRANT EXECUTE ON FUNCTION create_organization_with_owner(text, text, uuid) "
                f"TO {APP_DB_USER}"
            )
        )
        await conn.execute(
            text(
                f"GRANT USAGE ON TYPE membership_role, audit_action, "
                f"audit_resource_type TO {APP_DB_USER}"
            )
        )


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def admin_database_url(postgres_container: PostgresContainer) -> str:
    """Superuser URL. Used for migrations, truncate, and privilege grants."""
    url = _to_asyncpg_url(postgres_container.get_connection_url())
    _ensure_app_role_exists(url)
    _run_migrations(url)
    return url


@pytest_asyncio.fixture(scope="session")
async def admin_engine(admin_database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(admin_database_url, pool_pre_ping=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture(scope="session")
async def database_url(
    postgres_container: PostgresContainer,
    admin_engine: AsyncEngine,
    admin_database_url: str,
) -> str:
    await _grant_app_role_privileges(admin_engine, postgres_container.dbname)
    return _replace_url_credentials(admin_database_url, APP_DB_USER, APP_DB_PASSWORD)


@pytest_asyncio.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(database_url, pool_pre_ping=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(
    engine: AsyncEngine,
    admin_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # Truncate as superuser: app role has no TRUNCATE privilege by design.
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE {', '.join(TABLES_TO_TRUNCATE)} CASCADE")
        )

    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    yield factory


@pytest.fixture
def crypto_service() -> CryptoService:
    kms = LocalKMSProvider(master_key_str="test-master-key-for-unit-and-integration")
    return CryptoService(kms)


@pytest_asyncio.fixture
async def tenant(
    session_factory: async_sessionmaker[AsyncSession],
    crypto_service: CryptoService,
) -> TenantFixture:
    return await seed_tenant(session_factory, crypto_service)


@pytest_asyncio.fixture
async def uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantFixture,
):
    def _factory(
        user_id: str | None = None,
        org_id: str | None = None,
    ) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(
            user_id=user_id or str(tenant.user_id),
            org_id=org_id or str(tenant.org_id),
            session_factory=session_factory,
        )

    return _factory
