"""
Evaluation metrics computation module.

Computes accuracy, Jaccard similarity blast-radius match, faithfulness
(evidence grounding), and evaluation metrics.
"""

import json
from typing import Any

from pydantic import BaseModel, Field


class GoldenIncident(BaseModel):
    """Pydantic model representing a golden incident fixture."""

    incident_id: str
    service_id: str
    alert_message: str
    expected_root_cause: str
    expected_affected_services: list[str]
    expected_blast_radius: list[str]
    difficulty: str = "easy"
    tags: list[str] = Field(default_factory=list)


def compute_jaccard_similarity(set_a: list[str], set_b: list[str]) -> float:
    """Compute Jaccard similarity index between two list of items."""
    s1, s2 = set(set_a), set(set_b)
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return len(s1.intersection(s2)) / float(len(s1.union(s2)))


def compute_faithfulness_score(
    observability_analysis: str,
    collected_evidence: dict[str, Any],
) -> float:
    """Compute evidence-grounding faithfulness score.

    Checks whether the LLM observability_analysis references terms
    actually present in the collected evidence. Prevents hallucinated
    claims.

    Returns a score between 0.0 (no grounding) and 1.0 (fully grounded).
    """
    if not observability_analysis:
        return 0.0

    # Flatten all collected evidence into a single searchable text
    evidence_text = json.dumps(collected_evidence, default=str).lower()
    if not evidence_text or evidence_text == "{}":
        # No evidence was collected — can't ground anything
        return 0.0

    # Extract meaningful tokens from observability_analysis (>3 chars, not stopwords)
    stopwords = {
        "the", "and", "for", "was", "that", "this", "with", "from",
        "are", "were", "been", "have", "has", "had", "not", "but",
        "they", "their", "which", "when", "what", "there", "also",
        "into", "more", "than", "its", "can", "all", "will",
    }
    summary_tokens = [
        w for w in observability_analysis.lower().split()
        if len(w) > 3 and w not in stopwords
    ]

    if not summary_tokens:
        return 0.0

    # Count how many summary tokens appear in the raw evidence
    grounded_count = sum(1 for t in summary_tokens if t in evidence_text)
    return round(grounded_count / len(summary_tokens), 2)


def evaluate_incident_result(
    golden: GoldenIncident,
    predicted_root_cause: str,
    predicted_affected_services: list[str],
    predicted_blast_radius: list[str],
    confidence_score: float,
) -> dict[str, Any]:
    """Evaluate predicted orchestrator output against golden benchmark."""
    blast_radius_accuracy = compute_jaccard_similarity(
        golden.expected_blast_radius, predicted_blast_radius
    )
    affected_services_accuracy = compute_jaccard_similarity(
        golden.expected_affected_services, predicted_affected_services
    )

    # Keyword overlap heuristic for root cause match score
    expected_words = set(golden.expected_root_cause.lower().split())
    predicted_words = set(predicted_root_cause.lower().split())
    root_cause_overlap = (
        len(expected_words.intersection(predicted_words)) / max(len(expected_words), 1)
    )

    return {
        "incident_id": golden.incident_id,
        "service_id": golden.service_id,
        "blast_radius_accuracy": round(blast_radius_accuracy, 2),
        "affected_services_accuracy": round(affected_services_accuracy, 2),
        "root_cause_overlap_score": round(root_cause_overlap, 2),
        "confidence_score": confidence_score,
        "passed_evaluation": blast_radius_accuracy >= 0.5 and root_cause_overlap >= 0.2,
    }
