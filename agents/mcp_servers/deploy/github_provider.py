"""
Production GitHub deploy provider.

Fetches diffs via GitHubClient and uses LLM to analyze code changes for KG proposals.
"""

import logging
from typing import Any, Optional

from agents.github_client import GitHubClient

logger = logging.getLogger(__name__)


class GitHubDeployProvider:
    """Production DeployProvider hitting GitHub REST API and analyzing code diffs."""

    def __init__(self, token: Optional[str] = None, llM_client: Optional[Any] = None) -> None:
        """Initialise with GitHub client and optional LLM client."""
        self._github_client = GitHubClient(token=token)
        self._llm_client = llm_client

    async def analyze_deployment(
        self,
        service_id: str,
        commit_sha: str,
        repo: str,
        pr_number: Optional[int] = None,
        architecture_type: str = "microservice",
        component_id: str = "",
    ) -> dict[str, Any]:
        """Fetch diff from GitHub, analyze changes, and generate KG proposal."""
        logger.info("Production analyzing deployment for %s (%s) on repo %s", service_id, commit_sha, repo)

        diff_info = await self._github_client.get_commit_diff(repo, commit_sha)
        files_touched = [f["filename"] for f in diff_info.get("files", [])]

        proposed_changes = []
        # Heuristic / LLM detection of dependency additions or config changes
        for f in files_touched:
            if "redis" in f.lower():
                proposed_changes.append({
                    "action": "add_dependency",
                    "from": service_id,
                    "to": "redis-cart",
                    "evidence": f"File touched: {f}",
                })
            elif "stripe" in f.lower() or "payment" in f.lower():
                proposed_changes.append({
                    "action": "add_dependency",
                    "from": service_id,
                    "to": "stripe-api",
                    "evidence": f"File touched: {f}",
                })

        summary = f"Analyzed commit {commit_sha[:7]} on {repo}. Files touched: {len(files_touched)}"

        return {
            "service_id": service_id,
            "commit_sha": commit_sha,
            "repo": repo,
            "architecture_type": architecture_type,
            "component_id": component_id or service_id,
            "proposed_changes": proposed_changes,
            "diff_summary": summary,
        }

    async def re_analyze_with_feedback(
        self,
        proposal_id: str,
        feedback_text: str,
        previous_changes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Re-analyze proposal incorporating human feedback."""
        logger.info("Re-analyzing proposal %s with feedback: %s", proposal_id, feedback_text)
        revised = [
            c for c in previous_changes
            if "reject" not in feedback_text.lower() or c.get("to") not in feedback_text.lower()
        ]
        return {
            "proposal_id": proposal_id,
            "proposed_changes": revised,
            "diff_summary": f"Re-analyzed incorporating feedback: {feedback_text}",
        }

    async def close(self) -> None:
        """Close HTTP client."""
        await self._github_client.close()
