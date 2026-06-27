"""
In-process MCP client — MVP implementation.

Instead of connecting to separate MCP server processes over
stdio/SSE, this client directly instantiates the provider
objects (MockLogProvider, etc.) and routes ``call_tool``
to method calls on those objects.

Production replacement: an ``MCPProtocolClient`` that speaks
actual MCP protocol to remote servers.  Swap via factory.
"""

import asyncio
import logging
from typing import Any, Optional

from agents.config import AgentSettings
from agents.mcp_client.base import MCPClient, ToolDef

logger = logging.getLogger(__name__)


# ── Tool registry (server → tool_name → metadata) ───────

_LOGS_TOOLS: list[ToolDef] = [
    ToolDef(
        server="logs",
        name="search_logs",
        description=(
            "Search service logs by keyword. Returns log "
            "entries matching the query string."
        ),
        parameters={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service ID to search.",
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Keyword to match in log messages."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20).",
                    "default": 20,
                },
            },
            "required": ["service", "query"],
        },
    ),
    ToolDef(
        server="logs",
        name="get_traces",
        description=(
            "Retrieve distributed-trace spans for a service. "
            "Optionally filter by trace_id."
        ),
        parameters={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service ID.",
                },
                "trace_id": {
                    "type": "string",
                    "description": (
                        "Optional trace ID to filter."
                    ),
                },
            },
            "required": ["service"],
        },
    ),
    ToolDef(
        server="logs",
        name="get_errors",
        description=(
            "Get recent ERROR-level log entries for a service."
        ),
        parameters={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service ID.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10).",
                    "default": 10,
                },
            },
            "required": ["service"],
        },
    ),
]


class InProcessMCPClient:
    """MVP MCP client — direct Python calls to providers.

    Holds provider instances (LogProvider, etc.) and maps
    ``call_tool("logs", "search_logs", {...})`` to
    ``self._log_provider.search_logs(**args)``.
    """

    def __init__(self, config: AgentSettings) -> None:
        self._config = config
        self._log_provider: Any = None
        self._tools: dict[str, dict[str, ToolDef]] = {}
        self._initialized = False

    # ── Protocol: initialize ─────────────────────────────

    async def initialize(self) -> None:
        """Create all provider instances and register tools."""
        if self._initialized:
            return

        logger.info("Initializing in-process MCP client...")

        # --- Logs server ---
        from agents.mcp_servers.logs.factory import (
            create_log_provider,
        )

        self._log_provider = create_log_provider(self._config)
        self._register_tools(_LOGS_TOOLS)

        # --- Metrics server (Step 9+ placeholder) ---
        # from agents.mcp_servers.metrics.factory import ...
        # self._metrics_provider = ...
        # self._register_tools(_METRICS_TOOLS)

        # --- Code diff server (Step 9) ---
        # from agents.mcp_servers.code_diff.factory import ...
        # self._code_diff_provider = ...
        # self._register_tools(_CODE_DIFF_TOOLS)

        self._initialized = True
        tool_count = sum(
            len(t) for t in self._tools.values()
        )
        logger.info(
            "MCP client ready: %d servers, %d tools",
            len(self._tools),
            tool_count,
        )

    # ── Protocol: list_tools ─────────────────────────────

    def list_tools(
        self, server: Optional[str] = None
    ) -> list[ToolDef]:
        """Return available tools, optionally filtered."""
        self._ensure_initialized()

        if server:
            return list(
                self._tools.get(server, {}).values()
            )

        all_tools: list[ToolDef] = []
        for server_tools in self._tools.values():
            all_tools.extend(server_tools.values())
        return all_tools

    # ── Protocol: call_tool ──────────────────────────────

    async def call_tool(
        self,
        server: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Route tool call to the correct provider method."""
        self._ensure_initialized()

        # Validate server + tool exist
        if server not in self._tools:
            raise KeyError(
                f"Unknown MCP server: '{server}'. "
                f"Available: {list(self._tools.keys())}"
            )
        if tool_name not in self._tools[server]:
            available = list(self._tools[server].keys())
            raise KeyError(
                f"Unknown tool '{tool_name}' on server "
                f"'{server}'. Available: {available}"
            )

        # Dispatch to provider
        provider = self._get_provider(server)
        method = getattr(provider, tool_name, None)
        if method is None:
            raise KeyError(
                f"Provider for '{server}' has no method "
                f"'{tool_name}'"
            )

        logger.debug(
            "Calling %s.%s(%s)", server, tool_name, arguments
        )

        # Apply timeout from config
        timeout = self._config.TOOL_TIMEOUT_SECONDS
        try:
            result = await asyncio.wait_for(
                method(**arguments),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Tool {server}.{tool_name} timed out "
                f"after {timeout}s"
            )

        return result

    # ── Protocol: shutdown ───────────────────────────────

    async def shutdown(self) -> None:
        """Clean up resources."""
        logger.info("Shutting down MCP client")
        self._log_provider = None
        self._tools.clear()
        self._initialized = False

    # ── Internal helpers ─────────────────────────────────

    def _register_tools(self, tools: list[ToolDef]) -> None:
        """Add tools to the internal catalog."""
        for tool in tools:
            if tool.server not in self._tools:
                self._tools[tool.server] = {}
            self._tools[tool.server][tool.name] = tool

    def _get_provider(self, server: str) -> Any:
        """Return the provider instance for a server name."""
        providers = {
            "logs": self._log_provider,
            # "metrics": self._metrics_provider,
            # "code_diff": self._code_diff_provider,
        }
        provider = providers.get(server)
        if provider is None:
            raise KeyError(
                f"No provider for server '{server}'"
            )
        return provider

    def _ensure_initialized(self) -> None:
        """Raise if initialize() was not called."""
        if not self._initialized:
            raise RuntimeError(
                "MCPClient not initialized. "
                "Call await client.initialize() first."
            )
