from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, UpdatedAtMixin, UUIDMixin


class EncryptionKey(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "encryption_keys"
    __table_args__ = (
        sa.UniqueConstraint(
            "environment_id",
            "key_version",
            name="uq_key_version_per_env",
        ),
        sa.CheckConstraint(
            "algorithm IN ('AES-256-GCM')",
            name="chk_encryption_keys_algorithm",
        ),
        sa.Index(
            "idx_encryption_keys_env",
            "environment_id",
            postgresql_where=sa.text("is_active = true"),
        ),
        sa.Index(
            "uq_one_active_key_per_env",
            "environment_id",
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        ),
    )

    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    wrapped_dek: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    key_version: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("1"),
    )
    algorithm: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'AES-256-GCM'"),
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("true"),
    )
    rotated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Secret(Base, UUIDMixin, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "secrets"
    __table_args__ = (
        sa.UniqueConstraint(
            "environment_id",
            "key_name",
            name="uq_secret_key_per_env",
        ),
        sa.ForeignKeyConstraint(
            ["current_version_id"],
            ["secret_versions.id"],
            name="fk_secrets_current_version",
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        sa.Index(
            "idx_secrets_env",
            "environment_id",
            postgresql_where=sa.text("is_deleted = false"),
        ),
    )

    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    key_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_deleted: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class SecretVersion(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "secret_versions"
    __table_args__ = (
        sa.UniqueConstraint("secret_id", "version_number", name="uq_secret_version"),
        sa.UniqueConstraint(
            "encryption_key_id",
            "iv",
            name="uq_secret_versions_key_iv",
        ),
        sa.Index("idx_secret_versions_secret", "secret_id"),
    )

    secret_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("secrets.id", ondelete="CASCADE"),
        nullable=False,
    )
    encryption_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("encryption_keys.id"),
        nullable=False,
    )
    encrypted_value: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    iv: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    version_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
