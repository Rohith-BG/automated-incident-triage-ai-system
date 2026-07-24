"""Unit tests for the MockDeployProvider (CI/CD codebase analysis agent)."""

import pytest
from agents.mcp_servers.deploy.mock import MockDeployProvider


@pytest.fixture
def provider() -> MockDeployProvider:
    """Provide a configured MockDeployProvider."""
    return MockDeployProvider()


@pytest.mark.asyncio
async def test_analyze_deployment(provider: MockDeployProvider) -> None:
    """analyze_deployment() returns structured proposal."""
    res = await provider.analyze_deployment(
        service_id="payment-service",
        commit_sha="a3b5c7d",
        repo="Rohith-BG/payment-service",
    )
    assert res["service_id"] == "payment-service"
    assert res["commit_sha"] == "a3b5c7d"
    assert len(res["proposed_changes"]) > 0
    assert res["proposed_changes"][0]["to"] == "stripe-api"


@pytest.mark.asyncio
async def test_re_analyze_with_feedback(provider: MockDeployProvider) -> None:
    """re_analyze_with_feedback() revises proposal using feedback text."""
    previous = [{"action": "add_dependency", "from": "payment-service", "to": "stripe-api"}]
    res = await provider.re_analyze_with_feedback(
        proposal_id="prop-1",
        feedback_text="Also add note about Redis",
        previous_changes=previous,
    )
    assert res["proposal_id"] == "prop-1"
    assert len(res["proposed_changes"]) == 2
    assert "feedback" in res["diff_summary"]
