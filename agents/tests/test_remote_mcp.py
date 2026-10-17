"""Unit tests for Remote MCP Client and adapters (Neo4j Aura, AWS, GitHub)."""

import pytest
from unittest.mock import AsyncMock, patch

from agents.config import AgentSettings
from agents.mcp_client.remote_client import RemoteMCPClient
from agents.knowledge_graph.neo4j_mcp_store import Neo4jMCPStore
from agents.mcp_servers.observability.aws_mcp_provider import AWSRemoteMCPProvider
from agents.mcp_servers.code_diff.github_mcp_provider import GitHubMCPCodeDiffProvider
from agents.mcp_servers.deploy.github_mcp_provider import GitHubMCPDeployProvider


@pytest.fixture
def config() -> AgentSettings:
    """Fixture providing AgentSettings with remote MCP enabled."""
    return AgentSettings(
        ENVIRONMENT="dev",
        MCP_TRANSPORT="remote",
        KG_BACKEND="neo4j_mcp",
        OBSERVABILITY_BACKEND="mock",  # Active runtime mock
        DEPLOY_BACKEND="github_mcp",
        INCIDENT_KNOWLEDGE_BACKEND="mock",
        CODE_DIFF_BACKEND="github_mcp",
        REPO_INTELLIGENCE_BACKEND="github_mcp",
        NEO4J_MCP_URL="https://test-instance.mcp-instances.neo4j.io",
        NEO4J_MCP_TOKEN="test-token",
    )


@pytest.mark.asyncio
async def test_remote_mcp_client_hybrid_init(config: AgentSettings) -> None:
    """Test RemoteMCPClient initializes hybrid setup with mock observability + remote Neo4j."""
    client = RemoteMCPClient(config)
    await client.initialize()

    tools = client.list_tools()
    # 22 standard tools + 3 Neo4j Aura remote tools = 25 tools total
    assert len(tools) == 25

    neo4j_tools = client.list_tools(server="neo4j")
    assert len(neo4j_tools) == 3
    tool_names = [t.name for t in neo4j_tools]
    assert "read-cypher" in tool_names
    assert "write-cypher" in tool_names
    assert "get-schema" in tool_names

    # Test local mock observability route
    logs = await client.call_tool(
        server="observability",
        tool_name="search_logs",
        arguments={"service": "payment-service", "query": "Stripe"},
    )
    assert len(logs) > 0
    assert logs[0]["service"] == "payment-service"

    await client.shutdown()


@pytest.mark.asyncio
async def test_neo4j_mcp_store_transformers(config: AgentSettings) -> None:
    """Test Neo4jMCPStore transforms domain calls into read-cypher/write-cypher calls."""
    store = Neo4jMCPStore(config=config)

    # Mock execute_cypher method to simulate Aura MCP response
    with patch.object(store, "_execute_cypher", new_callable=AsyncMock) as mock_exec:
        # 1. Test get_dependencies
        mock_exec.return_value = [{"id": "auth-service"}, {"id": "inventory-service"}]
        deps = await store.get_dependencies("order-service")
        assert deps == ["auth-service", "inventory-service"]
        assert "MATCH (s:Service {id: $service_id})-[:DEPENDS_ON]->(d)" in mock_exec.call_args[0][0]

        # 2. Test get_blast_radius
        mock_exec.return_value = [{"id": "order-service"}, {"id": "frontend"}]
        blast = await store.get_blast_radius("order-service")
        assert blast == ["frontend", "order-service"]
        assert "DEPENDS_ON*0.." in mock_exec.call_args[0][0]

        # 3. Test get_service_info
        mock_exec.return_value = [{"s": {"id": "order-service", "oncall_slack": "#orders"}}]
        info = await store.get_service_info("order-service")
        assert info["id"] == "order-service"

        # 4. Test apply_mutations
        mock_exec.return_value = []
        result = await store.apply_mutations([
            {"action": "add_dependency", "from": "service-a", "to": "service-b"}
        ])
        assert result["applied"] == 1

    await store.close()


@pytest.mark.asyncio
async def test_aws_remote_mcp_provider_fallback(config: AgentSettings) -> None:
    """Test AWSRemoteMCPProvider falls back to mock when no mcp_client is provided."""
    provider = AWSRemoteMCPProvider(config=config)

    # Without mcp_client, search_logs should fall back to mock data
    logs = await provider.search_logs("payment-service", "Stripe")
    assert len(logs) > 0
    assert logs[0]["service"] == "payment-service"

    # Get errors should gracefully fall back to mock data
    errors = await provider.get_errors("payment-service")
    assert len(errors) > 0

    # Get metrics should gracefully fall back to mock data
    metrics = await provider.get_metrics("payment-service", metric_name="error_rate")
    assert len(metrics) > 0


@pytest.mark.asyncio
async def test_github_mcp_providers(config: AgentSettings) -> None:
    """Test GitHub MCP code diff and deploy providers with mock registry."""
    mock_registry = AsyncMock()
    mock_registry.get_repo_for_service.return_value = "org/payment-service"

    code_diff_provider = GitHubMCPCodeDiffProvider(config, registry_service=mock_registry)
    deploy_provider = GitHubMCPDeployProvider(config, kg_store=mock_registry)

    # Both providers initialize and resolve repo properly
    repo = await code_diff_provider._resolve_repo("payment-service")
    assert repo == "org/payment-service"

    deploy_repo = await deploy_provider._resolve_repo("payment-service")
    assert deploy_repo == "org/payment-service"

    await code_diff_provider.close()
    await deploy_provider.close()
