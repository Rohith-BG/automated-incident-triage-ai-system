"""
Database model for service registry.

Source of truth for service-to-repo mapping and service metadata.
Populated during onboarding; managed by admins.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .incident import generate_uuid, utc_now_naive


class ServiceRegistry(Base):
    """Registered service with its GitHub repo and metadata."""

    __tablename__ = "service_registry"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    service_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    repo: Mapped[str] = mapped_column(String(255), nullable=False)
    architecture_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="microservice"
    )
    owner_team: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    language: Mapped[str] = mapped_column(
        String(50), nullable=True
    )
    alert_threshold: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        default=utc_now_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=utc_now_naive, onupdate=utc_now_naive, nullable=False
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "service_id": self.service_id,
            "repo": self.repo,
            "architecture_type": self.architecture_type,
            "owner_team": self.owner_team,
            "language": self.language,
            "alert_threshold": self.alert_threshold,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
