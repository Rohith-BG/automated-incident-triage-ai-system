"""
Auth request/response schemas.

Pydantic v2 models for registration, login, token responses,
and user profile views.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ── Request schemas ──────────────────────────────────────


class RegisterRequest(BaseModel):
    """Payload for user registration."""

    email: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="User email address.",
        examples=["alice@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plain-text password (min 8 characters).",
    )
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Full display name.",
        examples=["Alice Smith"],
    )


class LoginRequest(BaseModel):
    """Payload for user login."""

    email: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Registered email address.",
    )
    password: str = Field(
        ...,
        min_length=1,
        description="Plain-text password.",
    )


# ── Response schemas ─────────────────────────────────────


class TokenResponse(BaseModel):
    """Access token returned after login or refresh."""

    access_token: str = Field(
        ...,
        description="JWT access token.",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always bearer).",
    )


class UserResponse(BaseModel):
    """Public user profile representation."""

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
