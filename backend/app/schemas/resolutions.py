"""
Incident resolution request/response schemas.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CreateResolutionRequest(BaseModel):
    """Payload for submitting an incident resolution report."""

    what_was_root_cause: str = Field(..., min_length=10, description="Short summary of the root cause in engineer's own words.")
    what_fixed_it: str = Field(..., min_length=10, description="Exact steps taken that worked to fix the issue.")
    time_to_resolve_min: int = Field(..., ge=1, description="Time taken to resolve the incident in minutes.")
    should_update_incident_knowledge: bool = Field(default=False, description="Flag indicating if runbook/incident knowledge needs updates.")
    incident_knowledge_id: Optional[str] = Field(default=None, description="Linked existing runbook/incident knowledge ID.")
    notes: Optional[str] = Field(default=None, description="Any additional notes.")


class ResolutionResponse(BaseModel):
    """Resolution details response."""

    id: str
    incident_id: str
    resolved_by: str
    what_was_root_cause: str
    what_fixed_it: str
    time_to_resolve_min: int
    should_update_incident_knowledge: bool
    incident_knowledge_id: Optional[str]
    notes: Optional[str]
    created_at: datetime

    model_config = {
        "from_attributes": True
    }
