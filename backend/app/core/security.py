"""
Security utilities for authentication.

Provides password hashing (raw bcrypt) and JWT
token creation / validation (python-jose).
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from .config import settings
from ..exceptions import UnauthorizedException

# ── Password hashing (using raw bcrypt) ────────────────


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt."""
    # Convert plain password to bytes
    password_bytes = plain.encode("utf-8")
    # Generate salt and hash the password
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    password_bytes = plain.encode("utf-8")
    hashed_bytes = hashed.encode("utf-8")
    try:
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


# ── JWT tokens ──────────────────────────────────────────


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a short-lived JWT access token.

    Args:
        data: Claims to encode (must include ``sub``).
        expires_delta: Custom expiry; defaults to config value.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    to_encode["type"] = "access"
    to_encode["jti"] = str(uuid.uuid4())
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create a long-lived JWT refresh token.

    Args:
        data: Claims to encode (must include ``sub``).

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode["exp"] = expire
    to_encode["type"] = "refresh"
    to_encode["jti"] = str(uuid.uuid4())
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Args:
        token: Encoded JWT string.

    Returns:
        Decoded claims dictionary.

    Raises:
        UnauthorizedException: If the token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("sub") is None:
            raise UnauthorizedException(
                "Token missing subject claim."
            )
        return payload
    except JWTError as exc:
        raise UnauthorizedException(
            "Could not validate credentials.",
            cause=exc,
        )
