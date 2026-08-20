from uuid import UUID

from app.models.audit import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    model_class = AuditLog

    def record(
        self,
        *,
        organization_id: UUID | str | None,
        user_id: UUID | str | None,
        action: str,
        resource_type: str,
        resource_id: UUID | str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_=metadata,
        )
        self.add(entry)
        return entry
