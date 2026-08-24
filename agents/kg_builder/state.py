"""
State definition for the Knowledge Graph bootstrap workflow.

Holds the discovered codebase targets, extracted facts (with
evidence), validated mutations, feedback loop state, and the
uncertainty log used to drive ask-when-unsure behaviour.
"""

from typing import Any

from pydantic import BaseModel, Field


class KgBootstrapState(BaseModel):
    """LangGraph state for the KG bootstrap pipeline."""

    # ── Intake inputs ─────────────────────────────────────
    architecture_type: str = Field(
        default="microservice",
        description="Architecture classification: 'microservice' or 'monolith'.",
    )
    source: str = Field(
        default="github_org",
        description="Bootstrap source: 'github_org', 'github_repo', or 'services_json'.",
    )
    org: str = Field(
        default="",
        description="GitHub organization scanned (when source == github_org).",
    )
    repo: str = Field(
        default="",
        description="GitHub repo slug (when source == github_repo).",
    )
    owner_team: str = Field(
        default="platform-team",
        description="Owner team applied to services that do not declare one.",
    )

    # ── Discovered targets ────────────────────────────────
    targets: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Repository targets: [{repo, name, language, service_id}].",
    )

    # ── Extracted facts (with evidence) ───────────────────
    extracted: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-repo extracted facts: dependencies, manifests, entry points.",
    )

    # ── Validated mutations ───────────────────────────────
    mutations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Validated, apply_mutations-compatible mutations with evidence.",
    )
    revision_mutations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Verified revision mutations produced from reviewer feedback.",
    )

    # ── Feedback loop state ───────────────────────────────
    feedback_text: str = Field(
        default="",
        description="Free-text reviewer feedback driving the revision loop.",
    )
    feedback_intent: str = Field(
        default="unknown",
        description="Parsed intent: add_dependency, remove_dependency, "
        "add_node, update_metadata, approve, reject, unknown.",
    )
    feedback_entities: list[str] = Field(
        default_factory=list,
        description="Entity mentions extracted from feedback text.",
    )
    feedback_resolution: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved entity -> canonical graph node id map.",
    )

    # ── Outputs ───────────────────────────────────────────
    diff_summary: str = Field(
        default="",
        description="Human-readable summary of proposed graph changes.",
    )
    uncertainty: list[str] = Field(
        default_factory=list,
        description="Evidence gaps, unverified claims, and ask-when-unsure notes.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Errors encountered during the run.",
    )
    proposal_id: str = Field(
        default="",
        description="KGChangeProposal id created by the backend for this run.",
    )
