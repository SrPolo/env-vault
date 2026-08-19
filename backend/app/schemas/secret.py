from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Conventional env-var naming: uppercase, digits and underscores, never leading digit.
KEY_NAME_PATTERN = r"^[A-Z_][A-Z0-9_]*$"


class SecretCreate(BaseModel):
    key_name: str = Field(min_length=1, max_length=255, pattern=KEY_NAME_PATTERN)
    value: str = Field(max_length=65536)


class SecretUpdate(BaseModel):
    """Updating a secret always creates a new version; only the value changes."""

    value: str = Field(max_length=65536)


class SecretRead(BaseModel):
    """
    Secret metadata. Deliberately excludes the value so that listing endpoints
    cannot leak plaintext; use SecretReveal for that, behind its own permission.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    environment_id: UUID
    key_name: str
    current_version_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class SecretVersionRead(BaseModel):
    """Version history metadata, without the encrypted payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    secret_id: UUID
    version_number: int
    created_by: UUID | None = None
    created_at: datetime


class SecretReveal(BaseModel):
    """Response of an explicit reveal. Requires 'member' role and is audited."""

    id: UUID
    key_name: str
    value: str
