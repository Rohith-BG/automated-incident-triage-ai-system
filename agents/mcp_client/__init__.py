"""
MCP client sub-package.

Provides the unified tool interface used by the orchestrator:

    from agents.mcp_client import create_mcp_client
    client = create_mcp_client(config)
    await client.initialize()
    tools = client.list_tools()
    result = await client.call_tool("logs", "search_logs", {...})
"""

from agents.mcp_client.base import MCPClient, ToolDef
from agents.mcp_client.factory import create_mcp_client

__all__ = ["MCPClient", "ToolDef", "create_mcp_client"]
