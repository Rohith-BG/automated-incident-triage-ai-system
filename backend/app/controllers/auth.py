"""
Auth controller — transport-layer mapping for auth endpoints.

Converts between Pydantic schemas and service calls.
No business logic or database access here.
"""

from ..models.user import User
from ..schemas.auth import (
    TokenResponse,
    UserListResponse,
    UserResponse,
)
from ..services.auth import AuthService


class AuthController:
    """Transport layer for authentication workflows."""

    def __init__(self, service: AuthService) -> None:
        self._service = service

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        role: str,
    ) -> UserResponse:
        """Register a new user and return the profile.

        Args:
            email: Unique email address.
            password: Plain-text password.
            full_name: Display name.
            role: RBAC role for the new user.

        Returns:
            UserResponse schema.
        """
        user = await self._service.register(
            email=email,
            password=password,
            full_name=full_name,
            role=role,
        )
        return self._to_user_response(user)

    async def login(
        self,
        *,
        email: str,
        password: str,
    ) -> tuple[UserResponse, str, str]:
        """Authenticate and return user + tokens.

        Returns:
            Tuple of (UserResponse, access_token, refresh_token).
        """
        user, access_token, refresh_token = (
            await self._service.login(
                email=email,
                password=password,
            )
        )
        return self._to_user_response(user), access_token, refresh_token

    async def refresh(
        self,
        refresh_token: str,
    ) -> tuple[str, str]:
        """Rotate tokens.

        Returns:
            Tuple of (new_access_token, new_refresh_token).
        """
        return await self._service.refresh(refresh_token)

    async def list_users(self) -> UserListResponse:
        """Return all users for the admin management table.

        Returns:
            UserListResponse with the full user list.
        """
        users = await self._service.list_users()
        return UserListResponse(
            users=[self._to_user_response(u) for u in users],
            total=len(users),
        )

    async def update_user(
        self,
        *,
        user_id: str,
        admin_id: str,
        full_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> UserResponse:
        """Update a user and return the updated profile.

        Args:
            user_id: Target user ID.
            admin_id: ID of the admin performing the update.
            full_name: New display name.
            role: New RBAC role.
            is_active: New active flag.

        Returns:
            UserResponse schema.
        """
        user = await self._service.update_user(
            user_id=user_id,
            admin_id=admin_id,
            full_name=full_name,
            role=role,
            is_active=is_active,
        )
        return self._to_user_response(user)

    @staticmethod
    def _to_user_response(user: User) -> UserResponse:
        """Convert a User model to the public response schema."""
        return UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )
