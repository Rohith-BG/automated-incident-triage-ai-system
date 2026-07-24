"""
Mock code diff provider for commits, diffs, and pull requests.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MockCodeDiffProvider:
    """Mock provider serving code changes and diffs mapped by service."""

    def __init__(self, data_path: Path) -> None:
        """Initialise with path to mock_code_diffs.json."""
        self._data_path = data_path
        self._cache: Optional[dict[str, Any]] = None

    async def _load(self) -> dict[str, Any]:
        """Load and cache the JSON fixture."""
        if self._cache is None:
            logger.debug("Loading mock code diffs from %s", self._data_path)
            with open(self._data_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
        return self._cache

    def _resolve_repo(self, service: str) -> str:
        """Map service name to mock fixture repo key."""
        if "payment" in service:
            return "Rohith-BG/payment-service"
        return f"Rohith-BG/{service}"

    async def get_recent_commits(
        self,
        service: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent commits for service."""
        repo = self._resolve_repo(service)
        data = await self._load()
        repo_data = data.get(repo, {})
        commits = repo_data.get("commits", [])
        return commits[:limit]

    async def get_commit_diff(
        self,
        service: str,
        commit_sha: str,
    ) -> dict[str, Any]:
        """Fetch diff stats and patches for commit on service."""
        repo = self._resolve_repo(service)
        data = await self._load()
        repo_data = data.get(repo, {})
        diffs = repo_data.get("diffs", {})
        if commit_sha in diffs:
            return diffs[commit_sha]
        return {
            "sha": commit_sha,
            "stats": {"additions": 0, "deletions": 0, "total": 0},
            "files": []
        }

    async def get_pr_changes(
        self,
        service: str,
        pr_number: int,
    ) -> dict[str, Any]:
        """Fetch files changed and diff info for a PR on service."""
        repo = self._resolve_repo(service)
        data = await self._load()
        repo_data = data.get(repo, {})
        prs = repo_data.get("prs", {})
        pr_str = str(pr_number)
        if pr_str in prs:
            return prs[pr_str]
        return {
            "pr_number": pr_number,
            "title": f"Pull Request #{pr_number}",
            "files": [],
            "diff": ""
        }
