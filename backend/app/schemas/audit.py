from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    user_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID | None
    metadata: dict | None = Field(None, validation_alias="metadata_")
    created_at: datetime
