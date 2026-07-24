"""
Auth service — authentication and registration business logic.

Orchestrates password hashing, credential verification, and
JWT token lifecycle. No direct database access.
"""

import logging

from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from ..enums import UserRole
from ..exceptions import ConflictException, UnauthorizedException
from ..models.user import User
from ..repositories.user import UserRepository

logger = logging.getLogger(__name__)


class AuthService:
    """Business logic for authentication workflows."""

    def __init__(self, repository: UserRepository) -> None:
        self._repo = repository

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
    ) -> User:
        """Register a new user.

        Args:
            email: Unique email address.
            password: Plain-text password (min 8 chars).
            full_name: Display name.

        Returns:
            Newly created User.

        Raises:
            ConflictException: If the email is already registered.
        """
        existing = await self._repo.get_by_email(email)
        if existing:
            logger.warning("Registration failed: Email '%s' is already registered", email)
            raise ConflictException(
                f"Email '{email}' is already registered."
            )

        hashed = hash_password(password)
        user = await self._repo.create(
            email=email,
            hashed_password=hashed,
            full_name=full_name,
            role=UserRole.TEAM_MEMBER,
        )
        logger.info("Registered new user %s (%s)", user.id, email)
        return user

    async def login(
        self,
        *,
        email: str,
        password: str,
    ) -> tuple[User, str, str]:
        """Authenticate a user and issue tokens.

        Args:
            email: Registered email.
            password: Plain-text password.

        Returns:
            Tuple of (user, access_token, refresh_token).

        Raises:
            UnauthorizedException: If credentials are invalid.
        """
        user = await self._repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            logger.warning("Login failed: Invalid credentials for email %s", email)
            raise UnauthorizedException("Invalid email or password.")

        if not user.is_active:
            logger.warning("Login failed: Account deactivated for email %s", email)
            raise UnauthorizedException("Account is deactivated.")

        token_data = {"sub": user.id, "role": user.role}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        logger.info("User %s (%s) logged in successfully", user.id, email)
        return user, access_token, refresh_token

    async def refresh(
        self,
        refresh_token: str,
    ) -> tuple[str, str]:
        """Rotate tokens using a valid refresh token.

        Args:
            refresh_token: Encoded JWT refresh token.

        Returns:
            Tuple of (new_access_token, new_refresh_token).

        Raises:
            UnauthorizedException: If the refresh token is
                invalid, expired, or the user is inactive.
        """
        payload = decode_token(refresh_token)

        if payload.get("type") != "refresh":
            logger.warning("Token rotation failed: JWT type is not 'refresh'")
            raise UnauthorizedException(
                "Invalid token type for refresh."
            )

        user_id = payload["sub"]
        user = await self._repo.get_by_id(user_id)
        if not user or not user.is_active:
            logger.warning("Token rotation failed: User ID %s not found or deactivated", user_id)
            raise UnauthorizedException(
                "User not found or deactivated."
            )

        token_data = {"sub": user.id, "role": user.role}
        new_access = create_access_token(token_data)
        new_refresh = create_refresh_token(token_data)
        logger.info("Token rotation completed successfully for user ID: %s", user_id)
        return new_access, new_refresh
