"""
Mock deploy provider for development and testing.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MockDeployProvider:
    """Mock implementation of DeployProvider generating fixture proposals."""

    def __init__(self, data_path: Optional[Any] = None) -> None:
        """Initialise mock provider."""
        self._data_path = data_path

    async def analyze_deployment(
        self,
        service_id: str,
        commit_sha: str,
        repo: str,
        pr_number: Optional[int] = None,
        architecture_type: str = "microservice",
        component_id: str = "",
    ) -> dict[str, Any]:
        """Return fixture proposal for analysis."""
        logger.info("Mock analyzing deployment for %s (%s)", service_id, commit_sha)
        proposed_changes = []
        if service_id == "payment-service":
            proposed_changes = [
                {
                    "action": "add_dependency",
                    "from": "payment-service",
                    "to": "stripe-api",
                    "evidence": "Detected new Stripe SDK client call in payment_service/views.py",
                }
            ]

        return {
            "service_id": service_id,
            "commit_sha": commit_sha,
            "repo": repo,
            "architecture_type": architecture_type,
            "component_id": component_id or service_id,
            "proposed_changes": proposed_changes,
            "diff_summary": f"Mock analyzed commit {commit_sha[:7]} for {service_id}",
        }

    async def re_analyze_with_feedback(
        self,
        proposal_id: str,
        feedback_text: str,
        previous_changes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return updated fixture proposal based on feedback."""
        logger.info("Mock re-analyzing proposal %s with feedback: %s", proposal_id, feedback_text)
        # Revised changes incorporates correction from feedback
        revised_changes = list(previous_changes)
        revised_changes.append({
            "action": "update_metadata",
            "node": "payment-service",
            "field": "note",
            "value": f"Adjusted based on feedback: {feedback_text}",
        })
        return {
            "proposal_id": proposal_id,
            "proposed_changes": revised_changes,
            "diff_summary": f"Revised with feedback: {feedback_text}",
        }
