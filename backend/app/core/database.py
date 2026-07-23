from collections.abc import AsyncGenerator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    echo=False,  # Set to True if we want to log SQL queries during development
    future=True,
)

async_session_maker = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def set_rls_context(
    session: AsyncSession, user_id: str | None = None, org_id: str | None = None
) -> None:
    """
    Sets PostgreSQL row-level security (RLS) contexts for the current transaction.
    Uses local (transaction-scoped) configuration so it resets automatically upon commit/rollback.

    Always writes both GUCs (empty string when unset) so pooled connections cannot
    leak a previous org/user into the next transaction. Policies must read them via
    app_setting_uuid() / NULLIF so '' does not break uuid casts.
    """
    await session.execute(
        sa.text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(user_id) if user_id else ""},
    )
    await session.execute(
        sa.text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id) if org_id else ""},
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to yield a database session per request.
    Ensures that the session is properly closed after the request completes.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
