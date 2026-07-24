"""
Database model for KG change proposals.

Stores deploy agent's proposed knowledge graph mutations
for human review and iterative feedback.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .incident import generate_uuid, utc_now_naive


class KGChangeProposal(Base):
    """A proposed set of knowledge graph mutations from the deploy agent."""

    __tablename__ = "kg_change_proposals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    service_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    commit_sha: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    repo: Mapped[str] = mapped_column(String(255), nullable=False)
    architecture_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="microservice"
    )
    component_id: Mapped[str] = mapped_column(
        String(200), nullable=False
    )
    proposed_changes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False
    )
    diff_summary: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )
    admin_feedback: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    parent_proposal_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("kg_change_proposals.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        default=utc_now_naive, nullable=False
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "service_id": self.service_id,
            "commit_sha": self.commit_sha,
            "repo": self.repo,
            "architecture_type": self.architecture_type,
            "component_id": self.component_id,
            "proposed_changes": self.proposed_changes,
            "diff_summary": self.diff_summary,
            "status": self.status,
            "admin_feedback": self.admin_feedback,
            "parent_proposal_id": self.parent_proposal_id,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": (
                self.reviewed_at.isoformat()
                if self.reviewed_at
                else None
            ),
            "created_at": self.created_at.isoformat(),
        }
