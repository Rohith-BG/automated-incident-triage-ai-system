"""
Protocol interface for the MCP client.

The orchestrator depends only on this Protocol.
MVP uses in-process Python calls; production can swap
to actual MCP protocol over stdio/SSE without changing
orchestrator code.
"""

from typing import Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel


class ToolDef(BaseModel):
    """Metadata for a single tool exposed by an MCP server.

    Used by the orchestrator to discover available tools and
    by the LLM to build function-calling declarations.
    """

    server: str          # "logs", "metrics", "code_diff"
    name: str            # "search_logs"
    description: str     # Human-readable purpose
    parameters: dict[str, Any]  # JSON Schema for args


@runtime_checkable
class MCPClient(Protocol):
    """Unified interface to all MCP tool servers."""

    async def initialize(self) -> None:
        """Connect to / create all configured servers.

        Must be called once before list_tools or call_tool.
        """
        ...

    def list_tools(
        self, server: Optional[str] = None
    ) -> list[ToolDef]:
        """Return available tools.

        Args:
            server: If given, filter to tools from that server
                    only (e.g. "logs").  None = all tools.

        Returns:
            List of ToolDef describing each tool.
        """
        ...

    async def call_tool(
        self,
        server: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Invoke a tool on the named server.

        Args:
            server: Server identifier ("logs", "metrics", …).
            tool_name: Tool function name ("search_logs").
            arguments: Keyword arguments for the tool.

        Returns:
            Tool result (type depends on the tool).

        Raises:
            KeyError: Unknown server or tool_name.
            TimeoutError: Tool did not respond in time.
        """
        ...

    async def shutdown(self) -> None:
        """Clean up connections / resources."""
        ...
