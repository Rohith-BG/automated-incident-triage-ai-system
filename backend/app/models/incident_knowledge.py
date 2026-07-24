"""
Database model for incident knowledge (pre-written SRE knowledge/runbooks).
"""

from datetime import datetime
from typing import Any
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from .incident import generate_uuid, utc_now_naive


class IncidentKnowledge(Base):
    """Pre-written SRE knowledge."""

    __tablename__ = "incident_knowledges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    applies_to_services: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    applies_to_error_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    symptoms: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    immediate_steps: Mapped[str] = mapped_column(Text, nullable=False)
    permanent_fix: Mapped[str] = mapped_column(Text, nullable=False)
    escalate_if: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_team: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=utc_now_naive, onupdate=utc_now_naive, nullable=False,
    )

    # Reverse relationship
    resolutions: Mapped[list["IncidentResolution"]] = relationship(
        "IncidentResolution", back_populates="incident_knowledge", lazy="selectin"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model representation to a dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "applies_to_services": self.applies_to_services,
            "applies_to_error_types": self.applies_to_error_types,
            "symptoms": self.symptoms,
            "root_cause_pattern": self.root_cause_pattern,
            "immediate_steps": self.immediate_steps,
            "permanent_fix": self.permanent_fix,
            "escalate_if": self.escalate_if,
            "owner_team": self.owner_team,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
