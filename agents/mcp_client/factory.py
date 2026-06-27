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
    # MVP: always in-process.  Future: check an env var
    # like MCP_MODE=protocol to use network transport.
    from agents.mcp_client.client import InProcessMCPClient

    return InProcessMCPClient(config)
