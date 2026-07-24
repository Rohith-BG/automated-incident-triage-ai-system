"""
Protocol interface for the code diff provider.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CodeDiffProvider(Protocol):
    """Code revision and diff contract for investigation triage."""

    async def get_recent_commits(
        self,
        service: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return a list of recent commit messages for *service*."""
        ...

    async def get_commit_diff(
        self,
        service: str,
        commit_sha: str,
    ) -> dict[str, Any]:
        """Return raw diff lines and patch statistics for *commit_sha* on *service*."""
        ...

    async def get_pr_changes(
        self,
        service: str,
        pr_number: int,
    ) -> dict[str, Any]:
        """Return file diffs and statistics for a Pull Request on *service*."""
        ...
