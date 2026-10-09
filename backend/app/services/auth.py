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
        role: UserRole = UserRole.DEVELOPER,
    ) -> User:
        """Register a new user.

        Called by admins only (route layer enforces RBAC). The admin
        chooses the role for the new user.

        Args:
            email: Unique email address.
            password: Plain-text password (min 8 chars).
            full_name: Display name.
            role: RBAC role assigned by the admin.

        Returns:
            Newly created User.

        Raises:
            ConflictException: If the email is already registered.
        """
        existing = await self._repo.get_by_email(email)
        if existing:
            logger.warning(
                "Registration failed: Email '%s' is already registered",
                email,
            )
            raise ConflictException(
                f"Email '{email}' is already registered."
            )

        # Bootstrap-admin: the very first account owns the platform and
        # can open the onboarding / initial-setup flow (build + review KG).
        # Every later registration is a plain team member.
        is_first_user = await self._repo.count() == 0
        role = UserRole.ADMIN if is_first_user else UserRole.TEAM_MEMBER

        hashed = hash_password(password)
        user = await self._repo.create(
            email=email,
            hashed_password=hashed,
            full_name=full_name,
            role=role,
        )
        logger.info("Registered new user %s (%s, role=%s)", user.id, email, role)
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

    async def list_users(self) -> list[User]:
        """Return all users.

        Called by admin-only route to populate the management table.

        Returns:
            List of all User instances.
        """
        return await self._repo.list_all()

    async def update_user(
        self,
        *,
        user_id: str,
        admin_id: str,
        full_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> User:
        """Update a user's profile fields.

        Args:
            user_id: Target user ID.
            admin_id: ID of the admin performing the update.
            full_name: New display name (optional).
            role: New RBAC role (optional).
            is_active: New active flag (optional).

        Returns:
            Updated User.

        Raises:
            NotFoundException: If user_id doesn't exist.
            BadRequestException: If admin tries to deactivate
                themselves.
        """
        from ..exceptions import BadRequestException, NotFoundException

        user = await self._repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"User '{user_id}' not found.")

        if is_active is False and user_id == admin_id:
            raise BadRequestException(
                "Cannot deactivate your own account."
            )

        if role is not None and role not in (
            UserRole.ADMIN,
            UserRole.DEVELOPER,
        ):
            raise BadRequestException(
                f"Invalid role '{role}'. Must be 'admin' or 'developer'."
            )

        updated = await self._repo.update(
            user,
            full_name=full_name,
            role=role,
            is_active=is_active,
        )
        logger.info(
            "Admin %s updated user %s (name=%s, role=%s, active=%s)",
            admin_id,
            user_id,
            full_name,
            role,
            is_active,
        )
        return updated
