from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, UpdatedAtMixin, UUIDMixin
from .enums import membership_role_enum


class Organization(Base, UUIDMixin, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    slug: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)


class Membership(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "memberships"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "organization_id", name="uq_membership"),
        sa.Index("idx_memberships_org", "organization_id"),
        sa.Index("idx_memberships_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        membership_role_enum,
        nullable=False,
        server_default=sa.text("'member'"),
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
