"""
Database model for platform users.

Defines the User table with bcrypt-hashed passwords and
role-based access control fields.
"""

from datetime import datetime, timezone
import uuid
from typing import Any

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from ..enums import UserRole


def _generate_uuid() -> str:
    """Generate a standard UUID string."""
    return str(uuid.uuid4())


def _utc_now_naive() -> datetime:
    """Timezone-naive UTC datetime for column defaults."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    """Platform user with role-based access control."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    full_name: Mapped[str] = mapped_column(
        String(200), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default=UserRole.TEAM_MEMBER
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        default=_utc_now_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=_utc_now_naive,
        onupdate=_utc_now_naive,
        nullable=False,
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert user to a dictionary (excludes password)."""
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
