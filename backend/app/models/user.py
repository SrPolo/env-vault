from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, UpdatedAtMixin, UUIDMixin


class User(Base, UUIDMixin, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint(
            "password_hash IS NOT NULL OR "
            "(oauth_provider IS NOT NULL AND oauth_subject IS NOT NULL)",
            name="chk_auth_method",
        ),
        sa.UniqueConstraint(
            "oauth_provider",
            "oauth_subject",
            name="uq_users_oauth_identity",
        ),
    )

    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(sa.Text)
    full_name: Mapped[str | None] = mapped_column(sa.Text)
    totp_secret: Mapped[str | None] = mapped_column(sa.Text)
    totp_enabled: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    oauth_provider: Mapped[str | None] = mapped_column(sa.Text)
    oauth_subject: Mapped[str | None] = mapped_column(sa.Text)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("true"),
    )


class RefreshToken(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        sa.Index(
            "idx_refresh_tokens_user",
            "user_id",
            postgresql_where=sa.text("revoked_at IS NULL"),
        ),
    )

    user_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    expires_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True))
