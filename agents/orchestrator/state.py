"""
State definition for the orchestrator.

Defines the structure of the data passed through the LangGraph
nodes during an incident investigation.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class RootCauseReport(BaseModel):
    """Structured report produced by the LLM synthesizer.

    Evidence is stored in discrete sections rather than a single
    flat string so consumers can render each category independently.
    """

    affected_services: list[str] = Field(
        default_factory=list,
        description="List of service IDs directly or transitively affected by the incident.",
    )
    raw_logs: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw log/trace data per service as fetched from the observability MCP server.",
    )
    raw_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw metric/anomaly data per service as fetched from the observability MCP server.",
    )
    observability_analysis: str = Field(
        default="",
        description="LLM-synthesized interpretation of logs, traces, and metrics evidence.",
    )
    code_diffs: dict[str, Any] = Field(
        default_factory=dict,
        description="Commit/diff data per service from the code_diff MCP server.",
    )
    past_resolutions: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Matching past resolutions for this incident's service. "
            "Empty list when no prior resolutions exist."
        ),
    )
    root_cause: str = Field(
        description="Detailed description of the identified root cause of the incident."
    )
    remediation_steps: list[str] = Field(
        default_factory=list,
        description="List of actionable remediation steps to resolve the issue.",
    )
    confidence_score: float = Field(
        description="Confidence score for the diagnosis, between 0.0 and 1.0."
    )
    uncertainty: str = Field(
        default="",
        description="Known evidence gaps or low-confidence aspects of the investigation.",
    )


class InvestigationState(BaseModel):
    """LangGraph state representation for the incident investigation."""

    # Intake inputs
    incident_id: str = Field(description="Unique ID of the incident.")
    service_id: str = Field(description="The source service ID that raised the alert.")
    alert_message: str = Field(description="The alert payload or error message description.")

    # Architecture dispatch (Rule 25)
    architecture_type: str = Field(
        default="microservice",
        description="Architecture classification: 'microservice' or 'monolith'.",
    )
    entry_point: str = Field(
        default="",
        description="Graph entry node for KG queries. "
        "service_id for microservices, module path for monoliths.",
    )

    # Knowledge Graph context (populated in Step 1)
    blast_radius: list[str] = Field(
        default_factory=list,
        description="List of all upstream/downstream services in the blast radius.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Services that the source service directly depends on.",
    )
    owner_team: dict[str, str] = Field(
        default_factory=dict,
        description="Owner team information including contact and slack channel.",
    )
    historical_incidents: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of historical incidents on this service.",
    )

    # Gathered evidence (populated in Step 2 parallel nodes)
    log_evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Collected logs, traces, and error patterns indexed by service.",
    )
    metrics_evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Collected metric series and anomaly detectors indexed by service.",
    )
    deploy_evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Collected recent deployment details indexed by service.",
    )
    incident_knowledge_evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Matching playbooks, runbooks, and past resolutions.",
    )
    code_evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Collected git commits and pull request diffs indexed by service.",
    )

    # Synthesis result (populated in Step 3)
    report: Optional[RootCauseReport] = Field(
        default=None,
        description="The synthesized root cause report.",
    )

    # Gating output (populated in Step 4)
    confidence_gate_passed: Optional[bool] = Field(
        default=None,
        description="True if confidence score is >= threshold, False otherwise.",
    )
