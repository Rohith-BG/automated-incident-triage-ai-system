"""
Shared GitHub API async client utility.

Used by both Deploy and CodeDiff MCP providers for GitHub API communication.
"""

import logging
from typing import Any, Optional
import httpx

logger = logging.getLogger(__name__)


class GitHubClient:
    """Async HTTP wrapper for GitHub REST API calls."""

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        """Initialise httpx client with headers and configurable base_url."""
        from agents.config import agent_settings

        self._token = token
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        resolved_base_url = base_url or agent_settings.GITHUB_API_BASE_URL

        self._client = httpx.AsyncClient(
            base_url=resolved_base_url,
            headers=headers,
            timeout=30.0,
        )

    async def get_commits(self, repo: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent commits for a repo."""
        url = f"/repos/{repo}/commits"
        logger.info("Fetching commits from GitHub: %s", url)
        try:
            resp = await self._client.get(url, params={"per_page": limit})
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            commits = resp.json()
            return [
                {
                    "sha": c.get("sha", ""),
                    "author": c.get("commit", {}).get("author", {}).get("email", "unknown"),
                    "date": c.get("commit", {}).get("author", {}).get("date", ""),
                    "message": c.get("commit", {}).get("message", ""),
                }
                for c in commits
            ]
        except Exception as e:
            logger.error("Failed to fetch commits for %s: %s", repo, e)
            return []

    async def get_commit_diff(self, repo: str, commit_sha: str) -> dict[str, Any]:
        """Fetch diff and files touched by a commit."""
        url = f"/repos/{repo}/commits/{commit_sha}"
        logger.info("Fetching commit diff from GitHub: %s", url)
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            c = resp.json()
            files = [
                {"filename": f.get("filename"), "patch": f.get("patch", "")}
                for f in c.get("files", [])
            ]
            return {
                "sha": commit_sha,
                "stats": c.get("stats", {"additions": 0, "deletions": 0, "total": 0}),
                "files": files,
            }
        except Exception as e:
            logger.error("Failed to fetch commit diff for %s/%s: %s", repo, commit_sha, e)
            return {"sha": commit_sha, "stats": {"additions": 0, "deletions": 0, "total": 0}, "files": []}

    async def get_pr_changes(self, repo: str, pr_number: int) -> dict[str, Any]:
        """Fetch PR files and diffs."""
        url = f"/repos/{repo}/pulls/{pr_number}/files"
        logger.info("Fetching PR changes from GitHub: %s", url)
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            files_data = resp.json()
            files = [f.get("filename") for f in files_data]
            diff_lines = [
                f"File: {f.get('filename')}\n{f.get('patch', '')}"
                for f in files_data
                if f.get("patch")
            ]
            return {
                "pr_number": pr_number,
                "title": f"Pull Request #{pr_number}",
                "files": files,
                "diff": "\n\n".join(diff_lines),
            }
        except Exception as e:
            logger.error("Failed to fetch PR changes for %s#%s: %s", repo, pr_number, e)
            return {"pr_number": pr_number, "title": f"Pull Request #{pr_number}", "files": [], "diff": ""}

    async def close(self) -> None:
        """Close AsyncClient."""
        await self._client.aclose()
