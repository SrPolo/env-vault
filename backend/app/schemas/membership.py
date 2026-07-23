from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class MembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class MembershipInvite(BaseModel):
    email: EmailStr
    role: MembershipRole = MembershipRole.MEMBER


class MembershipUpdateRole(BaseModel):
    role: MembershipRole


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    organization_id: UUID
    role: MembershipRole
    invited_by: UUID | None = None
    created_at: datetime
