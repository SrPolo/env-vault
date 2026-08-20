from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt

from app.core.config import settings

ACCESS_TOKEN_TYPE = "access"


def create_access_token(
    user_id: UUID | str,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate an access JWT.

    Raises jwt.PyJWTError subclasses on failure (expired, invalid signature, etc.).
    """
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Token is not an access token.")
    if not payload.get("sub"):
        raise jwt.InvalidTokenError("Token subject is missing.")
    return payload


def generate_refresh_token() -> str:
    """Opaque high-entropy refresh token. Store only its hash."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    """SHA-256 hex digest. Refresh tokens are high-entropy; Argon2 is unnecessary."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_token_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
