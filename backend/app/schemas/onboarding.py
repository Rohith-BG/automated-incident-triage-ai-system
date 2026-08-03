"""
Onboarding & Service Topology Auto-Discovery Pydantic schemas.

Defines payloads for topology discovery requests, discovered service
definitions, and onboarding results.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class DiscoveredServiceInput(BaseModel):
    """Inline service specification provided during discovery."""

    service_id: str = Field(
        ...,
        description="Unique identifier of the service or module (e.g. 'cart-service', 'auth_module').",
    )
    repo: str = Field(
        "googlecloudplatform/microservices-demo",
        description="Repository URL or slug for the service.",
    )
    architecture_type: Literal["microservice", "monolith", "module"] = Field(
        "microservice",
        description="Architecture classification of the node.",
    )
    language: Optional[str] = Field(
        None,
        description="Primary programming language (e.g., 'Python', 'Go', 'Node.js').",
    )
    owner_team_id: Optional[str] = Field(
        None,
        description="ID of the owning engineering team.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="List of service IDs or databases this node directly depends on.",
    )
    alert_threshold: Optional[str] = Field(
        "medium",
        description="Alert severity threshold ('low', 'medium', 'high', 'critical').",
    )


class DiscoverTopologyRequest(BaseModel):
    """Payload for triggering service topology discovery."""

    architecture_type: Literal["microservice", "monolith"] = Field(
        "microservice",
        description="Primary system architecture layout.",
    )
    source_type: Literal["inline", "services_json"] = Field(
        "services_json",
        description="Discovery source: 'inline' array or existing 'services_json' data file.",
    )
    owner_team_id: str = Field(
        "platform-team",
        description="Default owner team ID applied to newly discovered services.",
    )
    services: list[DiscoveredServiceInput] = Field(
        default_factory=list,
        description="Optional list of services provided directly when source_type='inline'.",
    )


class DiscoveredServiceSummary(BaseModel):
    """Summary of a single discovered service."""

    service_id: str
    architecture_type: str
    owner_team_id: str
    dependencies: list[str]
    is_new: bool


class OnboardingResultResponse(BaseModel):
    """Response returned upon completing service topology discovery."""

    discovered_count: int = Field(
        ...,
        description="Total number of services/modules identified.",
    )
    registered_count: int = Field(
        ...,
        description="Number of services registered or updated in the service registry.",
    )
    proposal_id: Optional[str] = Field(
        None,
        description="ID of the generated Knowledge Graph change proposal (status=pending).",
    )
    discovered_services: list[DiscoveredServiceSummary] = Field(
        default_factory=list,
        description="Detailed list of discovered services.",
    )
    message: str = Field(
        ...,
        description="Human-readable result summary and next steps.",
    )


class OnboardingStatusResponse(BaseModel):
    """Status summary of overall topology onboarding."""

    total_registered_services: int
    pending_proposals_count: int
    active_services_count: int
