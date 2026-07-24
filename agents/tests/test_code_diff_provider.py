"""Unit tests for the MockCodeDiffProvider (service resolution)."""

import pytest
from pathlib import Path
from agents.mcp_servers.code_diff.mock import MockCodeDiffProvider

PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def provider() -> MockCodeDiffProvider:
    """Provide a configured MockCodeDiffProvider."""
    return MockCodeDiffProvider(data_path=PROJECT_ROOT / "data" / "mock_code_diffs.json")


@pytest.mark.asyncio
async def test_get_recent_commits(provider: MockCodeDiffProvider) -> None:
    """get_recent_commits() returns commits using service_id."""
    commits = await provider.get_recent_commits("payment-service")
    assert len(commits) == 2
    assert commits[0]["sha"] == "a3b5c7d"


@pytest.mark.asyncio
async def test_get_commit_diff(provider: MockCodeDiffProvider) -> None:
    """get_commit_diff() returns raw patch metadata using service_id."""
    diff = await provider.get_commit_diff("payment-service", "a3b5c7d")
    assert diff["sha"] == "a3b5c7d"
    assert diff["stats"]["total"] == 17
    assert len(diff["files"]) == 1
    assert "amount" in diff["files"][0]["patch"]


@pytest.mark.asyncio
async def test_get_pr_changes(provider: MockCodeDiffProvider) -> None:
    """get_pr_changes() returns changes associated with PR ID using service_id."""
    changes = await provider.get_pr_changes("payment-service", 42)
    assert changes["pr_number"] == 42
    assert "payment_service/views.py" in changes["files"]
