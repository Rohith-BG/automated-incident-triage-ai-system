"""
FastAPI route handlers for in-app notifications.
"""

from typing import Any

from fastapi import APIRouter, Depends, Path, Query

from ..dependencies import get_current_user, get_notification_service
from ..models.user import User
from ..schemas.notification import (
    NotificationListResponse,
    NotificationMarkReadResponse,
    NotificationResponse,
)
from ..services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> Any:
    """List the current user's in-app notifications."""
    notifications = await service.list_for_user(
        user_email=current_user.email, limit=limit, unread_only=unread_only
    )
    unread = await service.list_for_user(
        user_email=current_user.email, limit=200, unread_only=True
    )
    return {
        "notifications": notifications,
        "total": len(notifications),
        "unread": len(unread),
    }


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
)
async def mark_read(
    notification_id: str = Path(...),
    service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Mark a single notification as read."""
    return await service.mark_read(notification_id)


@router.post(
    "/read-all",
    response_model=NotificationMarkReadResponse,
)
async def mark_all_read(
    service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Mark all of the current user's notifications as read."""
    marked = await service.mark_all_read(current_user.email)
    return {"marked": marked}


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: str = Path(...),
    service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a single notification."""
    await service.delete(notification_id)
