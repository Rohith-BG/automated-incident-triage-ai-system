"""Unit tests for the in-process MCPClient."""

import pytest
from agents.config import AgentSettings
from agents.mcp_client.client import InProcessMCPClient


@pytest.fixture
def client() -> InProcessMCPClient:
    """Provide a configured InProcessMCPClient."""
    config = AgentSettings(
        ENVIRONMENT="dev",
        OBSERVABILITY_BACKEND="mock",
        DEPLOY_BACKEND="mock",
        INCIDENT_KNOWLEDGE_BACKEND="mock",
        CODE_DIFF_BACKEND="mock",
        REPO_INTELLIGENCE_BACKEND="mock",
    )
    return InProcessMCPClient(config)


@pytest.mark.asyncio
async def test_mcp_client_workflow(client: InProcessMCPClient) -> None:
    """Test client initialization, list_tools, and call_tool workflows."""
    # 1. initialize client
    await client.initialize()

    # 2. list_tools verifies registration
    tools = client.list_tools()
    # 5 observability, 3 deploy, 4 incident_knowledge, 3 code_diff,
    # 7 repo_intelligence = 22 tools total
    assert len(tools) == 22

    # Filtered tool listing
    obs_tools = client.list_tools(server="observability")
    assert len(obs_tools) == 5

    # Deploy tools registered (including get_recent_deploys)
    deploy_tools = client.list_tools(server="deploy")
    assert len(deploy_tools) == 3

    # Repo intelligence tools registered (KG bootstrap server)
    ri_tools = client.list_tools(server="repo_intelligence")
    assert len(ri_tools) == 7

    # 3. Call tool on observability server
    logs = await client.call_tool(
        server="observability",
        tool_name="search_logs",
        arguments={"service": "payment-service", "query": "Stripe"},
    )
    assert len(logs) > 0
    assert logs[0]["service"] == "payment-service"

    # 4. Call tool on deploy server (analyze_deployment)
    analysis = await client.call_tool(
        server="deploy",
        tool_name="analyze_deployment",
        arguments={
            "service_id": "payment-service",
            "commit_sha": "a3b5c7d",
            "repo": "Rohith-BG/payment-service",
        },
    )
    assert analysis["service_id"] == "payment-service"
    assert len(analysis["proposed_changes"]) > 0

    # 4b. Call tool on deploy server (get_recent_deploys)
    recent_deploys = await client.call_tool(
        server="deploy",
        tool_name="get_recent_deploys",
        arguments={"service": "payment-service", "limit": 5},
    )
    assert len(recent_deploys) == 2
    assert recent_deploys[0]["deploy_id"] == "dep-101"

    # 5. Call tool on incident_knowledge server
    runbooks = await client.call_tool(
        server="incident_knowledge",
        tool_name="search_incident_knowledge",
        arguments={"service": "payment-service", "error_type": "stripe_api_timeout"},
    )
    assert len(runbooks) == 1
    assert runbooks[0]["id"] == "rb-1"

    # 6. Call tool on code_diff server using service parameter
    commits = await client.call_tool(
        server="code_diff",
        tool_name="get_recent_commits",
        arguments={"service": "payment-service"},
    )
    assert len(commits) == 2
    assert commits[0]["sha"] == "a3b5c7d"

    await client.shutdown()
