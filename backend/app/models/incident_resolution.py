"""
Database model for post-incident resolutions.
"""

from datetime import datetime
from typing import Any, Optional
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from .incident import generate_uuid, utc_now_naive


class IncidentResolution(Base):
    """Post-incident knowledge. Engineer fills after resolving."""

    __tablename__ = "incident_resolutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True,
    )
    resolved_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    what_was_root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    what_fixed_it: Mapped[str] = mapped_column(Text, nullable=False)
    time_to_resolve_min: Mapped[int] = mapped_column(nullable=False)
    should_update_incident_knowledge: Mapped[bool] = mapped_column(default=False, nullable=False)
    incident_knowledge_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("incident_knowledges.id"), nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now_naive, nullable=False)

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="resolution")
    resolved_by_user: Mapped["User"] = relationship("User")
    incident_knowledge: Mapped[Optional["IncidentKnowledge"]] = relationship("IncidentKnowledge", back_populates="resolutions")

    def to_dict(self) -> dict[str, Any]:
        """Convert model representation to a dictionary."""
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "resolved_by": self.resolved_by,
            "what_was_root_cause": self.what_was_root_cause,
            "what_fixed_it": self.what_fixed_it,
            "time_to_resolve_min": self.time_to_resolve_min,
            "should_update_incident_knowledge": self.should_update_incident_knowledge,
            "incident_knowledge_id": self.incident_knowledge_id,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }
