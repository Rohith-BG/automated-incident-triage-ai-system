"""
Dashboard summary schemas.

Pydantic v2 models returned by the dashboard summary endpoint.
All aggregate figures are computed server-side from the incident
repository and the service catalog — the frontend never derives
counts itself.
"""

from pydantic import BaseModel, Field


class IncidentSummaryMetrics(BaseModel):
    """Aggregate incident counts for the operations board."""

    active: int = Field(
        description="Incidents currently investigating or with a root cause identified."
    )
    resolved_today: int = Field(
        description="Incidents resolved or completed since the start of today (UTC)."
    )


class ServiceHealthMetrics(BaseModel):
    """Per-service health classification derived from active incidents."""

    healthy: int = Field(description="Services with no active incidents.")
    degraded: int = Field(description="Services with exactly one active incident.")
    critical: int = Field(description="Services with two or more active incidents.")
    total: int = Field(description="Total number of known services.")


class DashboardSummaryResponse(BaseModel):
    """Top-level aggregate readout for the operations dashboard."""

    incident_summary: IncidentSummaryMetrics
    service_health: ServiceHealthMetrics
