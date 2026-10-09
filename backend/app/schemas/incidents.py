"""
Incident request/response schemas.

Pydantic v2 models for the incidents REST API.
All external payloads and responses are validated through these.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ..enums import IncidentStatus
from .resolutions import ResolutionResponse


# ── Request schemas ──────────────────────────────────────


class IngestAlertRequest(BaseModel):
    """Payload for ingesting a new alert into the triage system."""

    service_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Identifier of the service raising the alert.",
        examples=["cart-service"],
    )
    alert_message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Detailed error message from the alert.",
        examples=["Redis connection lost: ECONNREFUSED 127.0.0.1:6379"],
    )


# ── Response schemas ─────────────────────────────────────


class IngestAlertResponse(BaseModel):
    """Response after an alert has been ingested."""

    incident_id: str = Field(
        ...,
        description="ID of the incident this alert belongs to.",
    )
    status: str = Field(
        ...,
        description="Current incident status.",
    )
    is_new: bool = Field(
        ...,
        description=(
            "True if a new incident was created. "
            "False if the alert was attached to an existing active incident."
        ),
    )


class AlertResponse(BaseModel):
    """Single alert in an incident detail view."""

    id: str
    incident_id: str
    alert_message: str
    created_at: datetime


class ReportResponse(BaseModel):
    """Root-cause report attached to a completed incident."""

    id: str
    root_cause: str
    affected_services: list[str]
    raw_logs: dict = Field(default_factory=dict)
    raw_metrics: dict = Field(default_factory=dict)
    observability_analysis: str = ""
    code_diffs: dict = Field(default_factory=dict)
    past_resolutions: list[dict] = Field(default_factory=list)
    remediation_steps: list[str]
    confidence_score: float
    created_at: datetime


class IncidentSummaryResponse(BaseModel):
    """Lightweight incident representation for list views."""

    id: str
    service_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    alert_count: int = Field(
        default=0,
        description="Number of alerts attached to this incident.",
    )


class IncidentDetailResponse(BaseModel):
    """Full incident detail including alerts and report."""

    id: str
    service_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    alerts: list[AlertResponse] = Field(default_factory=list)
    report: Optional[ReportResponse] = None
    resolution: Optional[ResolutionResponse] = None


class IncidentListResponse(BaseModel):
    """Cursor-paginated list of incidents."""

    items: list[IncidentSummaryResponse]
    next_cursor: Optional[str] = Field(
        None,
        description=(
            "Opaque cursor for the next page. "
            "Pass as ?cursor= to fetch more. "
            "None when there are no more results."
        ),
    )
    has_more: bool = Field(
        description="True if more pages exist beyond this one.",
    )
    limit: int = Field(
        description="Maximum items returned per page.",
    )
