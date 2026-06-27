"""
State definition for the orchestrator.

Defines the structure of the data passed through the LangGraph
nodes during an incident investigation.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class RootCauseReport(BaseModel):
    """Structured report produced by the LLM synthesizer."""

    root_cause: str = Field(
        description="Detailed description of the identified root cause of the incident."
    )
    evidence_summary: str = Field(
        description="Summary of log and trace evidence supporting this finding."
    )
    affected_services: list[str] = Field(
        default_factory=list,
        description="List of service IDs directly or transitively affected by the incident.",
    )
    remediation_steps: list[str] = Field(
        default_factory=list,
        description="List of actionable remediation steps to resolve the issue.",
    )
    confidence_score: float = Field(
        description="Confidence score for the diagnosis, between 0.0 and 1.0."
    )


class InvestigationState(BaseModel):
    """LangGraph state representation for the incident investigation."""

    # Intake inputs
    incident_id: str = Field(description="Unique ID of the incident.")
    service_id: str = Field(description="The source service ID that raised the alert.")
    alert_message: str = Field(description="The alert payload or error message description.")

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
    code_evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Collected git commits and pull request diffs indexed by service/repo.",
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
