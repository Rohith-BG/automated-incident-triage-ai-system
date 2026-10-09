"""
Pydantic schemas for the KG bootstrap trigger endpoints.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class KgBootstrapRunRequest(BaseModel):
    """Request payload to trigger a KG bootstrap run."""

    source: Optional[str] = Field(
        default=None,
        description="'github_org', 'github_repo', or 'services_json' "
        "(defaults to agent config).",
    )
    org: Optional[str] = Field(
        default=None, description="GitHub org when source == 'github_org'."
    )
    repo: Optional[str] = Field(
        default=None, description="Repo slug when source == 'github_repo'."
    )
    architecture_type: Optional[str] = Field(
        default=None, description="'microservice' or 'monolith'."
    )


class KgBootstrapRunResponse(BaseModel):
    """Response after dispatching a bootstrap run."""

    status: str = "started"


class KgBootstrapStatusResponse(BaseModel):
    """Status driving the 'Build KG' CTA."""

    needs_bootstrap: bool
    has_active_graph: bool
    bootstrap_enabled: bool = True
    pending_proposal_id: Optional[str] = None
    approved_proposal_id: Optional[str] = None
    pending_count: int = 0
    source: Optional[str] = None
    repo: Optional[str] = None
    org: Optional[str] = None
    architecture_type: Optional[str] = None
    owner_team: Optional[str] = None


class KgNode(BaseModel):
    """A staged graph node."""

    id: str
    kind: str = "service"
    properties: dict[str, Any] = Field(default_factory=dict)


class KgEdge(BaseModel):
    """A graph edge."""

    from_node: str = Field(alias="from")
    to: str
    type: str = "DEPENDS_ON"
    evidence: str = ""

    model_config = {"populate_by_name": True}



class KgStagingSnapshotResponse(BaseModel):
    """The currently staged graph."""

    nodes: list[KgNode] = Field(default_factory=list)
    edges: list[KgEdge] = Field(default_factory=list)
