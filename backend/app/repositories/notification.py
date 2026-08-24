"""
Repository for notification database operations.
"""

from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.notification import Notification


class NotificationRepository:
    """Database access layer for in-app notifications."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with database session."""
        self._session = session

    async def create(
        self,
        user_email: str,
        category: str,
        title: str,
        message: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> Notification:
        """Create and store a new notification."""
        notification = Notification(
            user_email=user_email,
            category=category,
            title=title,
            message=message,
            payload=payload,
        )
        self._session.add(notification)
        await self._session.flush()
        return notification

    async def list_for_user(
        self,
        user_email: str,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[Notification]:
        """List notifications for a user, newest first."""
        stmt = (
            select(Notification)
            .where(Notification.user_email == user_email)
            .order_by(Notification.created_at.desc())
        )
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, notification_id: str) -> Optional[Notification]:
        """Get a notification by ID."""
        stmt = select(Notification).where(Notification.id == notification_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_read(self, notification_id: str) -> Optional[Notification]:
        """Mark a single notification as read."""
        notification = await self.get_by_id(notification_id)
        if not notification:
            return None
        notification.is_read = True
        await self._session.flush()
        return notification

    async def mark_all_read(self, user_email: str) -> int:
        """Mark all notifications for a user as read."""
        stmt = (
            update(Notification)
            .where(Notification.user_email == user_email)
            .values(is_read=True)
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def delete(self, notification_id: str) -> bool:
        """Delete a notification by ID."""
        notification = await self.get_by_id(notification_id)
        if not notification:
            return False
        await self._session.delete(notification)
        await self._session.flush()
        return True
