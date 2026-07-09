from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, UUIDMixin
from .enums import audit_action_enum, audit_resource_type_enum


class AuditLog(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        sa.Index("idx_audit_logs_org", "organization_id", sa.text("created_at DESC")),
        sa.Index("idx_audit_logs_resource", "resource_type", "resource_id"),
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
