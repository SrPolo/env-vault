import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.uow import SqlAlchemyUnitOfWork
from app.services.auth import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)


@pytest.fixture
def auth_service() -> AuthService:
    return AuthService()


def _uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlAlchemyUnitOfWork:
    # Auth operates without RLS org context (users / refresh_tokens have no RLS).
    return SqlAlchemyUnitOfWork(
        user_id=None,
        org_id=None,
        session_factory=session_factory,
    )


@pytest.mark.asyncio
async def test_register_and_login(
    session_factory: async_sessionmaker[AsyncSession],
    auth_service: AuthService,
) -> None:
    async with _uow(session_factory) as uow:
        user = await auth_service.register(
            uow,
            email="alice@example.com",
            password="password123",
            full_name="Alice",
        )
        assert user.id is not None
        assert user.password_hash is not None
        assert user.password_hash != "password123"

    async with _uow(session_factory) as uow:
        logged_in, access, refresh = await auth_service.login(
            uow, email="alice@example.com", password="password123"
        )
    assert logged_in.email == "alice@example.com"
    assert access
    assert refresh


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(
    session_factory: async_sessionmaker[AsyncSession],
    auth_service: AuthService,
) -> None:
    async with _uow(session_factory) as uow:
        await auth_service.register(
            uow, email="dup@example.com", password="password123"
        )

    async with _uow(session_factory) as uow:
        with pytest.raises(EmailAlreadyRegisteredError):
            await auth_service.register(
                uow, email="dup@example.com", password="password123"
            )


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(
    session_factory: async_sessionmaker[AsyncSession],
    auth_service: AuthService,
) -> None:
    async with _uow(session_factory) as uow:
        await auth_service.register(
            uow, email="bob@example.com", password="password123"
        )

    async with _uow(session_factory) as uow:
        with pytest.raises(InvalidCredentialsError):
            await auth_service.login(
                uow, email="bob@example.com", password="wrong-password"
            )


@pytest.mark.asyncio
async def test_login_rejects_unknown_email(
    session_factory: async_sessionmaker[AsyncSession],
    auth_service: AuthService,
) -> None:
    async with _uow(session_factory) as uow:
        with pytest.raises(InvalidCredentialsError):
            await auth_service.login(
                uow, email="nobody@example.com", password="password123"
            )


@pytest.mark.asyncio
async def test_refresh_rotates_and_invalidates_old_token(
    session_factory: async_sessionmaker[AsyncSession],
    auth_service: AuthService,
) -> None:
    async with _uow(session_factory) as uow:
        await auth_service.register(
            uow, email="rotate@example.com", password="password123"
        )

    async with _uow(session_factory) as uow:
        _, _, refresh_1 = await auth_service.login(
            uow, email="rotate@example.com", password="password123"
        )

    async with _uow(session_factory) as uow:
        _, access_2, refresh_2 = await auth_service.refresh(
            uow, raw_refresh_token=refresh_1
        )

    assert access_2
    assert refresh_2 != refresh_1

    async with _uow(session_factory) as uow:
        with pytest.raises(InvalidRefreshTokenError):
            await auth_service.refresh(uow, raw_refresh_token=refresh_1)


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_all_user_tokens(
    session_factory: async_sessionmaker[AsyncSession],
    auth_service: AuthService,
) -> None:
    async with _uow(session_factory) as uow:
        await auth_service.register(
            uow, email="reuse@example.com", password="password123"
        )

    async with _uow(session_factory) as uow:
        user, _, refresh_a = await auth_service.login(
            uow, email="reuse@example.com", password="password123"
        )

    # Second device / session
    async with _uow(session_factory) as uow:
        _, _, refresh_b = await auth_service.login(
            uow, email="reuse@example.com", password="password123"
        )

    async with _uow(session_factory) as uow:
        _, _, refresh_a2 = await auth_service.refresh(
            uow, raw_refresh_token=refresh_a
        )

    # Replay of the already-rotated refresh_a triggers family wipe.
    async with _uow(session_factory) as uow:
        with pytest.raises(InvalidRefreshTokenError):
            await auth_service.refresh(uow, raw_refresh_token=refresh_a)

    async with _uow(session_factory) as uow:
        assert await uow.refresh_tokens.list_active_for_user(user.id) == []

    # Sibling session refresh_b is also dead.
    async with _uow(session_factory) as uow:
        with pytest.raises(InvalidRefreshTokenError):
            await auth_service.refresh(uow, raw_refresh_token=refresh_b)

    async with _uow(session_factory) as uow:
        with pytest.raises(InvalidRefreshTokenError):
            await auth_service.refresh(uow, raw_refresh_token=refresh_a2)


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(
    session_factory: async_sessionmaker[AsyncSession],
    auth_service: AuthService,
) -> None:
    async with _uow(session_factory) as uow:
        await auth_service.register(
            uow, email="logout@example.com", password="password123"
        )

    async with _uow(session_factory) as uow:
        _, _, refresh = await auth_service.login(
            uow, email="logout@example.com", password="password123"
        )

    async with _uow(session_factory) as uow:
        await auth_service.logout(uow, raw_refresh_token=refresh)

    async with _uow(session_factory) as uow:
        with pytest.raises(InvalidRefreshTokenError):
            await auth_service.refresh(uow, raw_refresh_token=refresh)

    # Idempotent second logout
    async with _uow(session_factory) as uow:
        await auth_service.logout(uow, raw_refresh_token=refresh)
