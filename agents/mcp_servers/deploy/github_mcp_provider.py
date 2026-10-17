"""
GitHub MCP Deploy Provider — queries GitHub MCP endpoint for deployments and workflow runs.

Connects to https://api.githubcopilot.com/mcp/ to retrieve GitHub Actions workflow runs
and recent deployments for a service, then analyzes code changes for KG proposals.
"""

import logging
from typing import Any, Optional

import httpx

from agents.config import AgentSettings
from agents.github_client import GitHubClient
from .base import DeployProvider

logger = logging.getLogger(__name__)


class GitHubMCPDeployProvider:
    """DeployProvider backed by GitHub MCP endpoint."""

    def __init__(
        self,
        config: AgentSettings,
        kg_store: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._mcp_url = config.GITHUB_MCP_URL
        self._token = config.GITHUB_TOKEN
        self._kg_store = kg_store
        self._http_client: Optional[httpx.AsyncClient] = None
        self._rest_fallback = GitHubClient(token=config.GITHUB_TOKEN)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._http_client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self._config.TOOL_TIMEOUT_SECONDS),
            )
        return self._http_client

    async def _resolve_repo(self, service: str) -> str:
        """Resolve service_id to repo slug via KnowledgeGraph."""
        if self._kg_store is None:
            from agents.knowledge_graph.factory import create_kg_store
            self._kg_store = create_kg_store(self._config)

        try:
            repo = await self._kg_store.get_repo_for_service(service)
            if repo:
                return repo
        except Exception as e:
            logger.warning("KG lookup failed for %s: %s", service, e)

        raise ValueError(
            f"Service '{service}' has no repo recorded in the knowledge graph. "
            "Run the KG bootstrap flow for this service first."
        )

    async def _call_mcp(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Send JSON-RPC tools/call to GitHub MCP server."""
        client = await self._get_client()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        resp = await client.post(self._mcp_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"GitHub MCP error: {data['error']}")
        return data.get("result", {})

    async def get_recent_deploys(
        self,
        service: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return recent deployments from GitHub Actions or recent commits via MCP."""
        repo = await self._resolve_repo(service)
        try:
            # Query GitHub MCP for workflow runs or deployments
            res = await self._call_mcp(
                "list_workflow_runs",
                {"repo": repo, "limit": limit},
            )
            if isinstance(res, dict) and "workflow_runs" in res:
                return [
                    {
                        "service": service,
                        "commit_sha": run.get("head_sha", ""),
                        "author": run.get("triggering_actor", {}).get("login", ""),
                        "timestamp": run.get("created_at", ""),
                        "message": run.get("display_title", run.get("name", "")),
                        "status": run.get("conclusion", run.get("status", "completed")),
                    }
                    for run in res["workflow_runs"][:limit]
                ]
        except Exception as e:
            logger.info(
                "GitHub MCP list_workflow_runs remote call failed, "
                "falling back to commit history via REST API: %s", e,
            )

        # Fallback to commit history as deployment records
        commits = await self._rest_fallback.get_commits(repo, limit=limit)
        return [
            {
                "service": service,
                "commit_sha": c.get("sha", ""),
                "author": c.get("author", ""),
                "timestamp": c.get("date", ""),
                "message": c.get("message", ""),
                "status": "deployed",
            }
            for c in commits
        ]

    async def analyze_deployment(
        self,
        service_id: str,
        commit_sha: str,
        repo: str,
        pr_number: Optional[int] = None,
        architecture_type: str = "microservice",
        component_id: str = "",
    ) -> dict[str, Any]:
        """Fetch diff from GitHub MCP/REST and generate KG proposal."""
        diff_info = await self._rest_fallback.get_commit_diff(repo, commit_sha)
        files_touched = [f["filename"] for f in diff_info.get("files", [])]

        proposed_changes = []
        for f in files_touched:
            f_lower = f.lower()
            if "redis" in f_lower:
                proposed_changes.append({
                    "action": "add_dependency",
                    "from": service_id,
                    "to": "redis-cart",
                    "evidence": f"File touched: {f}",
                })
            elif "stripe" in f_lower or "payment" in f_lower:
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
        """Re-analyze proposal with human feedback."""
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
        """Close clients."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        await self._rest_fallback.close()
