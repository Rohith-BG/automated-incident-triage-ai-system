"""
Factory for the MCP client.

MVP returns InProcessMCPClient (direct Python calls).
Production could return an MCPProtocolClient that speaks
MCP over stdio/SSE to remote server processes.
"""

from agents.config import AgentSettings
from agents.mcp_client.base import MCPClient


def create_mcp_client(
    config: AgentSettings,
) -> MCPClient:
    """Create and return the configured MCP client.

    Args:
        config: Agent settings.

    Returns:
        An MCPClient-compliant instance.

    Note:
        Caller must ``await client.initialize()`` before use.
    """
    if (
        config.uses_remote_mcp
        or config.OBSERVABILITY_BACKEND == "aws_mcp"
        or config.DEPLOY_BACKEND == "github_mcp"
        or config.CODE_DIFF_BACKEND == "github_mcp"
        or config.REPO_INTELLIGENCE_BACKEND == "github_mcp"
        or config.NEO4J_MCP_URL is not None
    ):
        from agents.mcp_client.remote_client import RemoteMCPClient

        return RemoteMCPClient(config)

    from agents.mcp_client.client import InProcessMCPClient

    return InProcessMCPClient(config)
