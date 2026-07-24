"""
Pydantic schemas for KG change proposals.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class KGProposalResponse(BaseModel):
    """Response schema for a KG change proposal."""

    id: str
    service_id: str
    commit_sha: str
    repo: str
    architecture_type: str
    component_id: str
    proposed_changes: list[dict[str, Any]]
    diff_summary: str
    status: str
    admin_feedback: Optional[str]
    parent_proposal_id: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class KGProposalFeedbackRequest(BaseModel):
    """Request schema for providing feedback on a proposal."""

    feedback: str = Field(
        ..., min_length=1, max_length=4000,
        description="Correction feedback for the deploy agent.",
    )
