from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.security.passwords import hash_password, verify_password_or_dummy
from app.core.security.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expires_at,
)
from app.core.uow import AbstractUnitOfWork
from app.models.user import RefreshToken, User


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """Generic auth failure — never distinguish unknown email vs bad password."""

    pass


class InactiveUserError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


class AuthService:
    """
    Registration, login, refresh-token rotation, and logout.

    Uses a UoW without org context: users and refresh_tokens have no RLS.
    """

    async def register(
        self,
        uow: AbstractUnitOfWork,
        *,
        email: str,
        password: str,
        full_name: str | None = None,
    ) -> User:
        existing = await uow.users.get_by_email(email)
        if existing is not None:
            raise EmailAlreadyRegisteredError(
                f"Email '{email}' is already registered."
            )

        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
        )
        uow.users.add(user)
        try:
            await uow.commit()
        except IntegrityError as exc:
            await uow.rollback()
            raise EmailAlreadyRegisteredError(
                f"Email '{email}' is already registered."
            ) from exc
        return user

    async def login(
        self,
        uow: AbstractUnitOfWork,
        *,
        email: str,
        password: str,
    ) -> tuple[User, str, str]:
        """
        Returns (user, access_token, refresh_token).

        Unknown email, wrong password, OAuth-only accounts, and inactive users
        all surface as InvalidCredentialsError (or InactiveUserError for the
        inactive case after a successful password check) to limit enumeration.
        """
        user = await uow.users.get_by_email(email)
        password_hash = user.password_hash if user is not None else None

        if not verify_password_or_dummy(password, password_hash):
            raise InvalidCredentialsError("Invalid email or password.")

        assert user is not None  # verified above via real hash

        if not user.is_active:
            raise InactiveUserError("User account is inactive.")

        access_token, refresh_token = await self._issue_token_pair(uow, user.id)
        return user, access_token, refresh_token

    async def refresh(
        self,
        uow: AbstractUnitOfWork,
        *,
        raw_refresh_token: str,
    ) -> tuple[User, str, str]:
        """
        Rotate the refresh token. Reuse of an already-revoked token revokes every
        active session for that user (theft detection).
        """
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = await uow.refresh_tokens.get_by_token_hash(token_hash)

        if stored is None:
            raise InvalidRefreshTokenError("Invalid refresh token.")

        if stored.revoked_at is not None:
            # Reuse detection: this token was already rotated — assume theft.
            await uow.refresh_tokens.revoke_all_for_user(stored.user_id)
            await uow.commit()
            raise InvalidRefreshTokenError("Refresh token reuse detected.")

        if stored.expires_at <= datetime.now(timezone.utc):
            await uow.refresh_tokens.revoke(stored.id)
            await uow.commit()
            raise InvalidRefreshTokenError("Refresh token has expired.")

        user = await uow.users.get(stored.user_id)
        if user is None or not user.is_active:
            await uow.refresh_tokens.revoke_all_for_user(stored.user_id)
            await uow.commit()
            raise InvalidRefreshTokenError("Invalid refresh token.")

        await uow.refresh_tokens.revoke(stored.id)
        access_token, refresh_token = await self._issue_token_pair(uow, user.id)
        return user, access_token, refresh_token

    async def logout(
        self,
        uow: AbstractUnitOfWork,
        *,
        raw_refresh_token: str,
    ) -> None:
        """Revoke a single refresh token. Idempotent if already unknown/revoked."""
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = await uow.refresh_tokens.get_by_token_hash(token_hash)
        if stored is None or stored.revoked_at is not None:
            return
        await uow.refresh_tokens.revoke(stored.id)
        await uow.commit()

    async def logout_all(
        self,
        uow: AbstractUnitOfWork,
        *,
        user_id: UUID | str,
    ) -> None:
        await uow.refresh_tokens.revoke_all_for_user(user_id)
        await uow.commit()

    async def _issue_token_pair(
        self,
        uow: AbstractUnitOfWork,
        user_id: UUID | str,
    ) -> tuple[str, str]:
        raw_refresh = generate_refresh_token()
        uow.refresh_tokens.add(
            RefreshToken(
                user_id=user_id,
                token_hash=hash_refresh_token(raw_refresh),
                expires_at=refresh_token_expires_at(),
            )
        )
        await uow.commit()
        return create_access_token(user_id), raw_refresh


__all__ = [
    "AuthService",
    "EmailAlreadyRegisteredError",
    "InvalidCredentialsError",
    "InactiveUserError",
    "InvalidRefreshTokenError",
]
