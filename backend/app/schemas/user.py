from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Base properties shared across user schemas."""

    email: EmailStr
    # Mirrors User.full_name, which is nullable (OAuth sign-ups may not provide it).
    full_name: str | None = Field(None, min_length=1, max_length=255)


class UserCreate(UserBase):
    """Properties required to create a user."""

    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    """Properties to receive via API on update."""

    email: EmailStr | None = None
    full_name: str | None = Field(None, min_length=1, max_length=255)
    password: str | None = Field(None, min_length=8, max_length=128)


class UserRead(UserBase):
    """Properties to return to client."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
