from datetime import timedelta
import time
import pytest
from jose import jwt

from backend.app.core.config import settings
from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from backend.app.exceptions import UnauthorizedException


def test_password_hashing_and_verification() -> None:
    """Test that password hashing and verification work correctly."""
    password = "super-secret-password"
    hashed = hash_password(password)

    # Check hash is different from plain text
    assert hashed != password
    assert hashed.startswith("$2b$")  # standard bcrypt prefix

    # Verify correct password
    assert verify_password(password, hashed) is True

    # Verify incorrect password
    assert verify_password("wrong-password", hashed) is False


def test_jwt_access_token_creation_and_decoding() -> None:
    """Test that access tokens can be created and decoded correctly."""
    data = {"sub": "user-id-123", "role": "sre"}
    token = create_access_token(data, expires_delta=timedelta(minutes=5))

    decoded = decode_token(token)

    assert decoded["sub"] == "user-id-123"
    assert decoded["role"] == "sre"
    assert decoded["type"] == "access"
    assert "exp" in decoded


def test_jwt_refresh_token_creation_and_decoding() -> None:
    """Test that refresh tokens can be created and decoded correctly."""
    data = {"sub": "user-id-123", "role": "team_member"}
    token = create_refresh_token(data)

    decoded = decode_token(token)

    assert decoded["sub"] == "user-id-123"
    assert decoded["role"] == "team_member"
    assert decoded["type"] == "refresh"
    assert "exp" in decoded


def test_decode_token_invalid_missing_sub() -> None:
    """Test that decode_token raises UnauthorizedException if sub claim is missing."""
    token = jwt.encode(
        {"role": "admin"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(UnauthorizedException) as exc_info:
        decode_token(token)

    assert "missing subject claim" in exc_info.value.message.lower()


def test_decode_token_invalid_signature() -> None:
    """Test that decode_token raises UnauthorizedException if signature is invalid."""
    token = create_access_token({"sub": "test"})
    bad_token = token + "corrupt"

    with pytest.raises(UnauthorizedException) as exc_info:
        decode_token(bad_token)

    assert "could not validate credentials" in exc_info.value.message.lower()


def test_decode_token_expired() -> None:
    """Test that decode_token raises UnauthorizedException on expired tokens."""
    # Create token expired 5 minutes ago
    data = {"sub": "user-id-123"}
    token = create_access_token(data, expires_delta=timedelta(minutes=-5))

    with pytest.raises(UnauthorizedException) as exc_info:
        decode_token(token)

    assert "could not validate credentials" in exc_info.value.message.lower()
