"""
Protocol interface for the deploy provider.
"""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class DeployProvider(Protocol):
    """Deployment codebase analyzer contract (CI/CD Deploy Agent)."""

    async def get_recent_deploys(
        self,
        service: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return recent deployments for a service.

        Used by the orchestrator's deploy investigation node to flag
        risky recent changes around the incident time window.
        """
        ...

    async def analyze_deployment(
        self,
        service_id: str,
        commit_sha: str,
        repo: str,
        pr_number: Optional[int] = None,
        architecture_type: str = "microservice",
        component_id: str = "",
    ) -> dict[str, Any]:
        """Analyze code changes in a deployment and generate a structured KG change proposal."""
        ...

    async def re_analyze_with_feedback(
        self,
        proposal_id: str,
        feedback_text: str,
        previous_changes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Re-analyze proposal with admin correction feedback and return revised proposal."""
        ...
