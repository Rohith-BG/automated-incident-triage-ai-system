"""
User repository — all user-related database access.

No business logic here. Only SQL queries and model persistence.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User

logger = logging.getLogger(__name__)


class UserRepository:
    """Data-access layer for User."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with an async database session."""
        self._session = session

    async def create(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str,
        role: str,
    ) -> User:
        """Insert a new user.

        Args:
            email: Unique email address.
            hashed_password: Bcrypt hash.
            full_name: Display name.
            role: RBAC role string.

        Returns:
            The newly created User.
        """
        user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        logger.info("Created user %s (%s)", user.id, email)
        return user

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Fetch a user by primary key.

        Returns:
            User instance, or None if not found.
        """
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch a user by email address.

        Returns:
            User instance, or None if not found.
        """
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count(self) -> int:
        """Count all registered users.

        Used to bootstrap the first user as platform admin.
        """
        stmt = select(User.id)
        result = await self._session.execute(stmt)
        return len(result.all())

    async def list_all(self) -> list[User]:
        """Return every user, ordered by creation date descending.

        Returns:
            List of User instances.
        """
        stmt = select(User).order_by(User.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        user: User,
        *,
        full_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> User:
        """Apply partial updates to a user row.

        Args:
            user: The User instance to mutate.
            full_name: New display name (if provided).
            role: New RBAC role (if provided).
            is_active: New active flag (if provided).

        Returns:
            The updated User.
        """
        if full_name is not None:
            user.full_name = full_name
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        await self._session.flush()
        await self._session.refresh(user)
        logger.info("Updated user %s", user.id)
        return user
