"""
Production GitHub REST API code diff provider using Service Registry resolution.
"""

import logging
from typing import Any, Optional

from agents.github_client import GitHubClient

logger = logging.getLogger(__name__)


class GitHubCodeDiffProvider:
    """Production CodeDiffProvider using GitHubClient and resolving service -> repo via registry."""

    def __init__(
        self,
        token: Optional[str] = None,
        registry_service: Optional[Any] = None,
    ) -> None:
        """Initialise with token and service registry dependency."""
        self._github_client = GitHubClient(token=token)
        self._registry_service = registry_service

    async def _get_repo(self, service: str) -> str:
        """Resolve service_id to repo slug via ServiceRegistry."""
        if self._registry_service:
            try:
                repo = await self._registry_service.get_repo_for_service(service)
                if repo:
                    return repo
            except Exception as e:
                logger.warning("ServiceRegistry lookup failed for %s: %s", service, e)

        raise ValueError(
            f"Service '{service}' is not registered in ServiceRegistry. "
            "Please onboard the service first."
        )

    async def get_recent_commits(
        self,
        service: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent commits for service."""
        repo = await self._get_repo(service)
        return await self._github_client.get_commits(repo, limit=limit)

    async def get_commit_diff(
        self,
        service: str,
        commit_sha: str,
    ) -> dict[str, Any]:
        """Fetch diff of commit for service."""
        repo = await self._get_repo(service)
        return await self._github_client.get_commit_diff(repo, commit_sha)

    async def get_pr_changes(
        self,
        service: str,
        pr_number: int,
    ) -> dict[str, Any]:
        """Fetch PR changes for service."""
        repo = await self._get_repo(service)
        return await self._github_client.get_pr_changes(repo, pr_number)

    async def close(self) -> None:
        """Close GitHub client."""
        await self._github_client.close()
