from pydantic import BaseModel


class Token(BaseModel):
    """Schema for returning JWT tokens."""

    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    """Payload to embed within the JWT token."""

    sub: str | None = None
