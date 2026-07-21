from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, UpdatedAtMixin, UUIDMixin


class Project(Base, UUIDMixin, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "projects"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "slug",
            name="uq_project_slug_per_org",
        ),
        sa.Index("idx_projects_org", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    slug: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )


class Environment(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "environments"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            "name",
            name="uq_environment_name_per_project",
        ),
        sa.Index("idx_environments_project", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)


class ApiToken(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "api_tokens"
    __table_args__ = (
        sa.Index(
            "idx_api_tokens_project",
            "project_id",
            postgresql_where=sa.text("revoked_at IS NULL"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
