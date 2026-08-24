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

    async def list_org_repos(
        self, org: str, per_page: int = 100
    ) -> list[dict[str, Any]]:
        """List repositories for a GitHub organization."""
        url = f"/orgs/{org}/repos"
        logger.info("Listing repositories for org %s", org)
        try:
            resp = await self._client.get(
                url, params={"per_page": per_page, "type": "all"}
            )
            resp.raise_for_status()
            return [
                {
                    "name": r.get("name", ""),
                    "repo": r.get("full_name", ""),
                    "language": r.get("language"),
                    "default_branch": r.get("default_branch", "main"),
                    "description": r.get("description", ""),
                }
                for r in resp.json()
            ]
        except Exception as e:
            logger.error("Failed to list repos for org %s: %s", org, e)
            return []

    async def get_repo_tree(
        self, repo: str, recursive: bool = True
    ) -> list[dict[str, Any]]:
        """Fetch the repository file tree via the git trees API."""
        url = f"/repos/{repo}/git/trees/HEAD"
        logger.info("Fetching repo tree for %s", repo)
        try:
            resp = await self._client.get(
                url, params={"recursive": "1" if recursive else "0"}
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            tree = resp.json().get("tree", [])
            return [
                {"path": t.get("path", ""), "type": t.get("type", "blob")}
                for t in tree
            ]
        except Exception as e:
            logger.error("Failed to fetch tree for %s: %s", repo, e)
            return []

    async def get_file_content(
        self, repo: str, path: str
    ) -> str:
        """Fetch the decoded content of a file in a repository."""
        url = f"/repos/{repo}/contents/{path}"
        logger.info("Fetching file %s from %s", path, repo)
        try:
            resp = await self._client.get(
                url, params={"ref": "HEAD"}
            )
            if resp.status_code == 404:
                return ""
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", "")
            if not content:
                return ""
            import base64
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception as e:
            logger.error("Failed to fetch file %s from %s: %s", path, repo, e)
            return ""

    async def get_repo_meta(self, repo: str) -> dict[str, Any]:
        """Fetch repository metadata."""
        url = f"/repos/{repo}"
        logger.info("Fetching repo metadata for %s", repo)
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return {
                "repo": data.get("full_name", repo),
                "default_branch": data.get("default_branch", "main"),
                "language": data.get("language"),
                "description": data.get("description", ""),
            }
        except Exception as e:
            logger.error("Failed to fetch repo metadata for %s: %s", repo, e)
            return {"repo": repo, "default_branch": "main", "language": None, "description": ""}

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
