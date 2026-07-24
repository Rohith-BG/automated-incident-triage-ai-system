"""
Logs MCP server sub-package.

Exposes the LogProvider protocol, the factory, and
convenience re-exports so consumers can do:

    from agents.mcp_servers.logs import create_log_provider
    provider = create_log_provider(config)
    errors = await provider.get_errors("frontend")
"""

from agents.mcp_servers.logs.base import LogProvider
from agents.mcp_servers.logs.factory import create_log_provider

__all__ = ["LogProvider", "create_log_provider"]
