"""
GitHub MCP Code Diff Provider — queries the remote GitHub MCP endpoint.

Connects to https://api.githubcopilot.com/mcp/ via Streamable HTTP JSON-RPC 2.0.
Resolves service -> repo via KnowledgeGraphStore and retrieves commits, diffs,
and PR changes.
"""

import logging
from typing import Any, Optional

import httpx

from agents.config import AgentSettings
from agents.github_client import GitHubClient
from .base import CodeDiffProvider

logger = logging.getLogger(__name__)


class GitHubMCPCodeDiffProvider:
    """CodeDiffProvider calling remote GitHub MCP server."""

    def __init__(
        self,
        config: AgentSettings,
        registry_service: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._mcp_url = config.GITHUB_MCP_URL
        self._token = config.GITHUB_TOKEN
        self._registry_service = registry_service
        self._http_client: Optional[httpx.AsyncClient] = None
        # Fallback client for direct REST queries if MCP tool schema differs
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
        """Resolve service_id to repo slug via registry."""
        if self._registry_service:
            try:
                repo = await self._registry_service.get_repo_for_service(service)
                if repo:
                    return repo
            except Exception as e:
                logger.warning("ServiceRegistry lookup failed for %s: %s", service, e)

        raise ValueError(
            f"Service '{service}' is not registered in KnowledgeGraph. "
            "Please onboard the service first."
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

    async def get_recent_commits(
        self,
        service: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent commits via GitHub MCP or fallback client."""
        repo = await self._resolve_repo(service)
        try:
            res = await self._call_mcp("list_commits", {"repo": repo, "limit": limit})
            if isinstance(res, list):
                return res
            if isinstance(res, dict) and "commits" in res:
                return res["commits"]
        except Exception as e:
            logger.info(
                "GitHub MCP list_commits remote call failed, "
                "falling back to direct GitHub REST API: %s", e,
            )

        return await self._rest_fallback.get_commits(repo, limit=limit)

    async def get_commit_diff(
        self,
        service: str,
        commit_sha: str,
    ) -> dict[str, Any]:
        """Fetch diff of commit via GitHub MCP or fallback client."""
        repo = await self._resolve_repo(service)
        try:
            res = await self._call_mcp("get_commit", {"repo": repo, "sha": commit_sha})
            if isinstance(res, dict) and "files" in res:
                return res
        except Exception as e:
            logger.info(
                "GitHub MCP get_commit remote call failed, "
                "falling back to direct GitHub REST API: %s", e,
            )

        return await self._rest_fallback.get_commit_diff(repo, commit_sha)

    async def get_pr_changes(
        self,
        service: str,
        pr_number: int,
    ) -> dict[str, Any]:
        """Fetch PR changes via GitHub MCP or fallback client."""
        repo = await self._resolve_repo(service)
        try:
            res = await self._call_mcp("get_pull_request", {"repo": repo, "pull_number": pr_number})
            if isinstance(res, dict) and "files" in res:
                return res
        except Exception as e:
            logger.info(
                "GitHub MCP get_pull_request remote call failed, "
                "falling back to direct GitHub REST API: %s", e,
            )

        return await self._rest_fallback.get_pr_changes(repo, pr_number)

    async def close(self) -> None:
        """Close clients."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        await self._rest_fallback.close()
