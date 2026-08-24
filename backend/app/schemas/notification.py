"""
Pydantic schemas for in-app notifications.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    """Response schema for a single notification."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_email: str
    category: str
    title: str
    message: str
    payload: Optional[dict[str, Any]] = None
    is_read: bool = False
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Response schema for a list of notifications."""

    notifications: list[NotificationResponse]
    total: int
    unread: int


class NotificationMarkReadResponse(BaseModel):
    """Response schema after marking notifications as read."""

    marked: int
