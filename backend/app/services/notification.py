"""
Service layer for in-app notifications.

Business logic for creating and reading notifications, plus a
boundary helper to persist + broadcast a notification over the
WebSocket channel. Only in-app delivery is used for the KG
bootstrap flow (NOTIFICATION_BACKEND stays untouched for future
incident notifications).
"""

import logging
from typing import Any, Optional

from ..exceptions import NotFoundException
from ..repositories.notification import NotificationRepository
from ..websocket import global_ws_manager

logger = logging.getLogger(__name__)


class NotificationService:
    """Service layer business logic for in-app notifications."""

    def __init__(self, repository: NotificationRepository) -> None:
        """Initialise with repository."""
        self._repository = repository

    async def create(
        self,
        user_email: str,
        category: str,
        title: str,
        message: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a notification and return its dict."""
        notification = await self._repository.create(
            user_email=user_email,
            category=category,
            title=title,
            message=message,
            payload=payload,
        )
        return notification.to_dict()

    async def notify_and_broadcast(
        self,
        user_email: str,
        category: str,
        title: str,
        message: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a notification and broadcast it over the WebSocket channel."""
        notification = await self.create(
            user_email=user_email,
            category=category,
            title=title,
            message=message,
            payload=payload,
        )
        await global_ws_manager.broadcast_event(
            "notifications",
            {"type": "notification", "notification": notification},
        )
        return notification

    async def list_for_user(
        self,
        user_email: str,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List notifications for a user."""
        notifications = await self._repository.list_for_user(
            user_email=user_email, limit=limit, unread_only=unread_only
        )
        return [n.to_dict() for n in notifications]

    async def mark_read(self, notification_id: str) -> dict[str, Any]:
        """Mark a notification as read."""
        notification = await self._repository.mark_read(notification_id)
        if not notification:
            raise NotFoundException(f"Notification '{notification_id}' not found.")
        return notification.to_dict()

    async def mark_all_read(self, user_email: str) -> int:
        """Mark all of a user's notifications as read."""
        return await self._repository.mark_all_read(user_email)

    async def delete(self, notification_id: str) -> None:
        """Delete a notification."""
        deleted = await self._repository.delete(notification_id)
        if not deleted:
            raise NotFoundException(f"Notification '{notification_id}' not found.")
