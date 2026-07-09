from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import BYTEA, CITEXT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


membership_role_enum = postgresql.ENUM(
    "owner",
    "admin",
    "member",
    "viewer",
    name="membership_role",
    create_type=False,
)

audit_action_enum = postgresql.ENUM(
    "create",
    "update",
    "delete",
    "reveal",
    "rollback",
    "login",
    "login_failed",
    "invite",
    "role_change",
    name="audit_action",
    create_type=False,
)

audit_resource_type_enum = postgresql.ENUM(
    "organization",
    "project",
    "environment",
    "secret",
    "membership",
    "api_token",
    name="audit_resource_type",
    create_type=False,
)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    slug: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


class User(Base):
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

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
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
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "organization_id", name="uq_membership"),
        sa.Index("idx_memberships_org", "organization_id"),
        sa.Index("idx_memberships_user", "user_id"),
    )

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        membership_role_enum,
        nullable=False,
        server_default=sa.text("'member'"),
    )
    invited_by: Mapped[sa.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "slug",
            name="uq_project_slug_per_org",
        ),
        sa.Index("idx_projects_org", "organization_id"),
    )

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    organization_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    slug: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text)
    created_by: Mapped[sa.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


class Environment(Base):
    __tablename__ = "environments"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            "name",
            name="uq_environment_name_per_project",
        ),
        sa.Index("idx_environments_project", "project_id"),
    )

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    project_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


class EncryptionKey(Base):
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

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    environment_id: Mapped[sa.UUID] = mapped_column(
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
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    rotated_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True))


class Secret(Base):
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

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    environment_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
    )
    key_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    current_version_id: Mapped[sa.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_deleted: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


class SecretVersion(Base):
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

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    secret_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("secrets.id", ondelete="CASCADE"),
        nullable=False,
    )
    encryption_key_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("encryption_keys.id"),
        nullable=False,
    )
    encrypted_value: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    iv: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    version_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_by: Mapped[sa.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (
        sa.Index(
            "idx_api_tokens_project",
            "project_id",
            postgresql_where=sa.text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    project_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_by: Mapped[sa.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    last_used_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True))
    expires_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        sa.Index(
            "idx_refresh_tokens_user",
            "user_id",
            postgresql_where=sa.text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    expires_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        sa.Index("idx_audit_logs_org", "organization_id", sa.text("created_at DESC")),
        sa.Index("idx_audit_logs_resource", "resource_type", "resource_id"),
    )

    id: Mapped[sa.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    organization_id: Mapped[sa.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="SET NULL"),
    )
    user_id: Mapped[sa.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(audit_action_enum, nullable=False)
    resource_type: Mapped[str] = mapped_column(audit_resource_type_enum, nullable=False)
    resource_id: Mapped[sa.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
