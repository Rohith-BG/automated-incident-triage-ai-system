"""
In-process MCP client — production-ready local execution.

Instantiates local provider instances (AWSObservabilityProvider, etc.) and routes
`call_tool` directly to python methods on those providers.
"""

import asyncio
import logging
from typing import Any, Optional

from agents.config import AgentSettings
from agents.mcp_client.base import MCPClient, ToolDef

logger = logging.getLogger(__name__)


# ── Tool registries ──────────────────────────────────────

_OBSERVABILITY_TOOLS: list[ToolDef] = [
    ToolDef(
        server="observability",
        name="search_logs",
        description="Search service logs by keyword.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID to search."},
                "query": {"type": "string", "description": "Keyword to match in log messages."},
                "limit": {"type": "integer", "description": "Max results (default 20).", "default": 20},
            },
            "required": ["service", "query"],
        },
    ),
    ToolDef(
        server="observability",
        name="get_errors",
        description="Get recent ERROR-level log entries for a service.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID."},
                "limit": {"type": "integer", "description": "Max results (default 10).", "default": 10},
            },
            "required": ["service"],
        },
    ),
    ToolDef(
        server="observability",
        name="get_traces",
        description="Retrieve log-based distributed trace spans for a service.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID."},
                "trace_id": {"type": "string", "description": "Optional trace ID to filter."},
            },
            "required": ["service"],
        },
    ),
    ToolDef(
        server="observability",
        name="get_metrics",
        description="Retrieve time-series metrics for a service.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID."},
                "metric_name": {"type": "string", "description": "Optional metric name filter (e.g. latency_ms)."},
                "minutes": {"type": "integer", "description": "Time window in minutes (default 60).", "default": 60},
            },
            "required": ["service"],
        },
    ),
    ToolDef(
        server="observability",
        name="get_anomalies",
        description="Retrieve detected metric anomalies for a service.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID."},
                "minutes": {"type": "integer", "description": "Time window in minutes (default 60).", "default": 60},
            },
            "required": ["service"],
        },
    ),
]

_DEPLOY_TOOLS: list[ToolDef] = [
    ToolDef(
        server="deploy",
        name="analyze_deployment",
        description="Analyze code changes in a deployment and generate a structured KG change proposal.",
        parameters={
            "type": "object",
            "properties": {
                "service_id": {"type": "string", "description": "Service or app identifier."},
                "commit_sha": {"type": "string", "description": "Full commit SHA deployed."},
                "repo": {"type": "string", "description": "GitHub repo slug (owner/repo)."},
                "pr_number": {"type": "integer", "description": "Optional PR number."},
                "architecture_type": {"type": "string", "description": "microservice, monolith, or module."},
                "component_id": {"type": "string", "description": "Component or module ID."},
            },
            "required": ["service_id", "commit_sha", "repo"],
        },
    ),
    ToolDef(
        server="deploy",
        name="re_analyze_with_feedback",
        description="Re-analyze proposal with human correction feedback.",
        parameters={
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string", "description": "Parent proposal ID."},
                "feedback_text": {"type": "string", "description": "Admin feedback text."},
                "previous_changes": {"type": "array", "description": "List of previous graph mutations."},
            },
            "required": ["proposal_id", "feedback_text", "previous_changes"],
        },
    ),
]

_INCIDENT_KNOWLEDGE_TOOLS: list[ToolDef] = [
    ToolDef(
        server="incident_knowledge",
        name="search_incident_knowledge",
        description="Search SRE playbooks/incident knowledge entries matching service, error type, and query keyword.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID."},
                "error_type": {"type": "string", "description": "Optional error type tag filter."},
                "query": {"type": "string", "description": "Optional search keyword to match in title or symptoms."},
                "limit": {"type": "integer", "description": "Max results (default 5).", "default": 5},
            },
            "required": ["service"],
        },
    ),
    ToolDef(
        server="incident_knowledge",
        name="get_incident_knowledge",
        description="Get detail of an incident knowledge entry by ID.",
        parameters={
            "type": "object",
            "properties": {
                "incident_knowledge_id": {"type": "string", "description": "Incident Knowledge ID."},
            },
            "required": ["incident_knowledge_id"],
        },
    ),
    ToolDef(
        server="incident_knowledge",
        name="get_past_resolutions",
        description="Return recent successful incident resolutions for a service.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID."},
                "limit": {"type": "integer", "description": "Max results (default 5).", "default": 5},
            },
            "required": ["service"],
        },
    ),
    ToolDef(
        server="incident_knowledge",
        name="get_similar_incidents",
        description="Return historical incidents with reports for a service.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID."},
                "error_pattern": {"type": "string", "description": "Optional pattern to search in report content."},
                "limit": {"type": "integer", "description": "Max results (default 5).", "default": 5},
            },
            "required": ["service"],
        },
    ),
]

_CODE_DIFF_TOOLS: list[ToolDef] = [
    ToolDef(
        server="code_diff",
        name="get_recent_commits",
        description="Return a list of recent commit messages and metadata for a service.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID."},
                "limit": {"type": "integer", "description": "Max results (default 10).", "default": 10},
            },
            "required": ["service"],
        },
    ),
    ToolDef(
        server="code_diff",
        name="get_commit_diff",
        description="Return raw diff lines and patch statistics for a specific commit on a service.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID."},
                "commit_sha": {"type": "string", "description": "Commit SHA hash."},
            },
            "required": ["service", "commit_sha"],
        },
    ),
    ToolDef(
        server="code_diff",
        name="get_pr_changes",
        description="Return file diffs and statistics for a specific Pull Request on a service.",
        parameters={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service ID."},
                "pr_number": {"type": "integer", "description": "Pull Request number."},
            },
            "required": ["service", "pr_number"],
        },
    ),
]


class InProcessMCPClient:
    """In-process MCP Client routing tool calls directly to providers."""

    def __init__(self, config: AgentSettings) -> None:
        """Initialise with settings."""
        self._config = config
        self._observability_provider: Any = None
        self._deploy_provider: Any = None
        self._incident_knowledge_provider: Any = None
        self._code_diff_provider: Any = None
        self._tools: dict[str, dict[str, ToolDef]] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Create all provider instances and register tools."""
        if self._initialized:
            return

        logger.info("Initializing in-process MCP client with 4 servers...")

        # 1. Observability
        from agents.mcp_servers.observability.factory import create_observability_provider
        self._observability_provider = create_observability_provider(self._config)
        self._register_tools(_OBSERVABILITY_TOOLS)

        # 2. Deploy
        from agents.mcp_servers.deploy.factory import create_deploy_provider
        self._deploy_provider = create_deploy_provider(self._config)
        self._register_tools(_DEPLOY_TOOLS)

        # 3. Incident Knowledge
        from agents.mcp_servers.incident_knowledge.factory import create_incident_knowledge_provider
        self._incident_knowledge_provider = create_incident_knowledge_provider(self._config)
        self._register_tools(_INCIDENT_KNOWLEDGE_TOOLS)

        # 4. Code Diff
        from agents.mcp_servers.code_diff.factory import create_code_diff_provider
        self._code_diff_provider = create_code_diff_provider(self._config)
        self._register_tools(_CODE_DIFF_TOOLS)

        self._initialized = True
        tool_count = sum(len(t) for t in self._tools.values())
        logger.info(
            "MCP client ready: %d servers, %d tools",
            len(self._tools),
            tool_count,
        )

    def list_tools(self, server: Optional[str] = None) -> list[ToolDef]:
        """Return available tools, optionally filtered by server."""
        self._ensure_initialized()
        if server:
            return list(self._tools.get(server, {}).values())

        all_tools: list[ToolDef] = []
        for server_tools in self._tools.values():
            all_tools.extend(server_tools.values())
        return all_tools

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

        provider = self._get_provider(server)
        method = getattr(provider, tool_name, None)
        if method is None:
            raise KeyError(f"Provider for '{server}' has no method '{tool_name}'")

        logger.debug("Calling %s.%s(%s)", server, tool_name, arguments)

        timeout = self._config.TOOL_TIMEOUT_SECONDS
        try:
            result = await asyncio.wait_for(
                method(**arguments),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Tool {server}.{tool_name} timed out after {timeout}s")

        return result

    async def shutdown(self) -> None:
        """Clean up resources."""
        logger.info("Shutting down MCP client")
        if self._code_diff_provider and hasattr(self._code_diff_provider, "close"):
            await self._code_diff_provider.close()
        if self._deploy_provider and hasattr(self._deploy_provider, "close"):
            await self._deploy_provider.close()

        self._observability_provider = None
        self._deploy_provider = None
        self._incident_knowledge_provider = None
        self._code_diff_provider = None
        self._tools.clear()
        self._initialized = False

    def _register_tools(self, tools: list[ToolDef]) -> None:
        """Add tools to the internal catalog."""
        for tool in tools:
            if tool.server not in self._tools:
                self._tools[tool.server] = {}
            self._tools[tool.server][tool.name] = tool

    def _get_provider(self, server: str) -> Any:
        """Return the provider instance for a server name."""
        providers = {
            "observability": self._observability_provider,
            "deploy": self._deploy_provider,
            "incident_knowledge": self._incident_knowledge_provider,
            "code_diff": self._code_diff_provider,
        }
        provider = providers.get(server)
        if provider is None:
            raise KeyError(f"No provider for server '{server}'")
        return provider

    def _ensure_initialized(self) -> None:
        """Raise if initialize() was not called."""
        if not self._initialized:
            raise RuntimeError(
                "MCPClient not initialized. "
                "Call await client.initialize() first."
            )
