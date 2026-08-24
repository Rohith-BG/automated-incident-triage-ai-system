"""
Database model for in-app notifications.

Stores notifications for the KG bootstrap human-in-the-loop flow
and other system events. Delivered in-app via the notifications
WebSocket channel and surfaced by GET /notifications.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .incident import generate_uuid, utc_now_naive


class Notification(Base):
    """A single in-app notification for a user."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_email: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="system", index=True
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    message: Mapped[str] = mapped_column(
        String(2000), nullable=False, default=""
    )
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        default=utc_now_naive, nullable=False
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_email": self.user_email,
            "category": self.category,
            "title": self.title,
            "message": self.message,
            "payload": self.payload,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat(),
        }
