"""
api/schemas/auth.py

Pydantic v2 models for auth request validation and response serialization.
These are the contracts between frontend and backend for all auth flows.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ─── Requests ─────────────────────────────────────────────────────────────────

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    timezone: str = "UTC"

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Basic password strength validation."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, v: str) -> str:
        import zoneinfo
        try:
            zoneinfo.ZoneInfo(v)
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            raise ValueError(f"Invalid timezone: {v}")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class OAuthCallbackRequest(BaseModel):
    """Sent by frontend after Google/Apple OAuth completes in Supabase."""
    supabase_token: str = Field(description="Token from Supabase after OAuth")
    timezone: str = "UTC"
    display_name: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ─── Responses ────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    """Returned after successful login, signup, or token refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires
    user: "UserSummary"


class UserSummary(BaseModel):
    """Minimal user info included in token responses."""
    id: UUID
    email: str
    display_name: str | None
    avatar_url: str | None
    onboarding_status: str
    onboarding_step: int
    timezone: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthErrorResponse(BaseModel):
    """Consistent error shape for all auth failures."""
    error: str
    detail: str
    request_id: str | None = None


# Update forward reference
TokenResponse.model_rebuild()
