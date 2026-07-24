"""
Incident knowledge request/response schemas.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CreateIncidentKnowledgeRequest(BaseModel):
    """Payload for creating a new SRE play/runbook entry."""

    title: str = Field(..., max_length=300, description="Title of the runbook/knowledge entry.")
    applies_to_services: list[str] = Field(..., description="List of service IDs this entry applies to.")
    applies_to_error_types: list[str] = Field(default_factory=list, description="List of error/exception types this entry targets.")
    symptoms: str = Field(..., description="Description of the symptoms.")
    root_cause_pattern: str = Field(..., description="Description of the root cause patterns.")
    immediate_steps: str = Field(..., description="Actionable SRE quick-fix/investigation steps.")
    permanent_fix: str = Field(..., description="Steps for permanent remediation.")
    escalate_if: str = Field(default="", description="Condition to trigger SRE team escalation.")
    owner_team: str = Field(..., max_length=100, description="Team owning this knowledge.")


class UpdateIncidentKnowledgeRequest(BaseModel):
    """Payload for updating an existing SRE knowledge entry."""

    title: Optional[str] = Field(None, max_length=300)
    applies_to_services: Optional[list[str]] = None
    applies_to_error_types: Optional[list[str]] = None
    symptoms: Optional[str] = None
    root_cause_pattern: Optional[str] = None
    immediate_steps: Optional[str] = None
    permanent_fix: Optional[str] = None
    escalate_if: Optional[str] = None
    owner_team: Optional[str] = Field(None, max_length=100)


class IncidentKnowledgeResponse(BaseModel):
    """Full detail response schema for SRE knowledge."""

    id: str
    title: str
    applies_to_services: list[str]
    applies_to_error_types: list[str]
    symptoms: str
    root_cause_pattern: str
    immediate_steps: str
    permanent_fix: str
    escalate_if: str
    owner_team: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class IncidentKnowledgeListResponse(BaseModel):
    """Cursor-paginated list of SRE knowledge."""

    items: list[IncidentKnowledgeResponse]
    next_cursor: Optional[str] = None
    has_more: bool
    limit: int
