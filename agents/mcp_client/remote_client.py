"""
Remote MCP Client — connects to official remote MCP servers over HTTP.

Supports:
- GitHub MCP: https://api.githubcopilot.com/mcp/
- AWS MCP: https://aws-mcp.<region>.api.aws/mcp
- Neo4j Aura MCP: https://<INSTANCE_ID>.mcp-instances.neo4j.io
- Hybrid fallback: routes local mock providers (e.g. mock observability)
  in-process without requiring cloud accounts.
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

from agents.config import AgentSettings
from agents.mcp_client.base import MCPClient, ToolDef
from agents.mcp_client.client import (
    _CODE_DIFF_TOOLS,
    _DEPLOY_TOOLS,
    _INCIDENT_KNOWLEDGE_TOOLS,
    _OBSERVABILITY_TOOLS,
    _REPO_INTELLIGENCE_TOOLS,
)

logger = logging.getLogger(__name__)


# Standard Neo4j Aura MCP tools exposed by the hosted server
_NEO4J_REMOTE_TOOLS: list[ToolDef] = [
    ToolDef(
        server="neo4j",
        name="read-cypher",
        description="Execute read-only Cypher query against Neo4j Aura.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Cypher query string"},
                "params": {"type": "object", "description": "Query parameters", "default": {}},
            },
            "required": ["query"],
        },
    ),
    ToolDef(
        server="neo4j",
        name="write-cypher",
        description="Execute write Cypher query against Neo4j Aura.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Cypher query string"},
                "params": {"type": "object", "description": "Query parameters", "default": {}},
            },
            "required": ["query"],
        },
    ),
    ToolDef(
        server="neo4j",
        name="get-schema",
        description="Get labels, relationship types, and properties in graph.",
        parameters={"type": "object", "properties": {}},
    ),
]


class RemoteServerEndpoint:
    """Configuration and transport for a single remote MCP server."""

    def __init__(
        self,
        name: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self._http_client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """Initialize HTTP client session."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    **self.headers,
                },
                timeout=httpx.Timeout(self.timeout, read=self.timeout * 2),
            )

    async def disconnect(self) -> None:
        """Close HTTP client session."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def call_tool_remote(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Invoke tool via MCP JSON-RPC 2.0 over Streamable HTTP."""
        if not self._http_client:
            await self.connect()

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        assert self._http_client is not None
        response = await self._http_client.post(self.url, json=payload)
        response.raise_for_status()

        data = response.json()
        if "error" in data:
            raise RuntimeError(
                f"MCP Remote Error on {self.name}.{tool_name}: {data['error']}"
            )

        result = data.get("result", {})
        # MCP specification: result can be a dict with 'content' array
        content = result.get("content")
        if isinstance(content, list):
            # Extract text or structured contents
            extracted = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    extracted.append(item["text"])
                else:
                    extracted.append(item)
            return extracted if len(extracted) > 1 else (extracted[0] if extracted else result)

        return result


class RemoteMCPClient:
    """Unified MCP client connecting to remote servers and local fallbacks."""

    def __init__(self, config: AgentSettings) -> None:
        self._config = config
        self._tools: dict[str, dict[str, ToolDef]] = {}
        self._remote_servers: dict[str, RemoteServerEndpoint] = {}

        # Local in-process fallback providers (for mock / dev mode)
        self._local_observability_provider: Any = None
        self._local_incident_knowledge_provider: Any = None
        self._local_code_diff_provider: Any = None
        self._local_deploy_provider: Any = None
        self._local_repo_intelligence_provider: Any = None

        self._initialized = False

    async def initialize(self) -> None:
        """Initialise remote connections and local fallback providers."""
        if self._initialized:
            return

        logger.info("Initializing RemoteMCPClient...")

        # 1. Observability: Remote AWS MCP or local mock
        if self._config.OBSERVABILITY_BACKEND == "aws_mcp":
            self._remote_servers["observability"] = RemoteServerEndpoint(
                name="observability",
                url=self._config.aws_mcp_url,
                timeout=float(self._config.TOOL_TIMEOUT_SECONDS),
            )
            await self._remote_servers["observability"].connect()
            self._register_tools(_OBSERVABILITY_TOOLS)
        else:
            # Local mock/cloudwatch provider
            from agents.mcp_servers.observability.factory import create_observability_provider
            self._local_observability_provider = create_observability_provider(self._config)
            self._register_tools(_OBSERVABILITY_TOOLS)

        # 2. Deploy: Remote GitHub MCP, AWS MCP, or local
        if self._config.DEPLOY_BACKEND == "github_mcp":
            headers = {}
            if self._config.GITHUB_TOKEN:
                headers["Authorization"] = f"Bearer {self._config.GITHUB_TOKEN}"
            self._remote_servers["deploy"] = RemoteServerEndpoint(
                name="deploy",
                url=self._config.GITHUB_MCP_URL,
                headers=headers,
                timeout=float(self._config.TOOL_TIMEOUT_SECONDS),
            )
            await self._remote_servers["deploy"].connect()
            self._register_tools(_DEPLOY_TOOLS)
        else:
            from agents.mcp_servers.deploy.factory import create_deploy_provider
            self._local_deploy_provider = create_deploy_provider(self._config)
            self._register_tools(_DEPLOY_TOOLS)

        # 3. Code Diff: Remote GitHub MCP or local
        if self._config.CODE_DIFF_BACKEND == "github_mcp":
            headers = {}
            if self._config.GITHUB_TOKEN:
                headers["Authorization"] = f"Bearer {self._config.GITHUB_TOKEN}"
            self._remote_servers["code_diff"] = RemoteServerEndpoint(
                name="code_diff",
                url=self._config.GITHUB_MCP_URL,
                headers=headers,
                timeout=float(self._config.TOOL_TIMEOUT_SECONDS),
            )
            await self._remote_servers["code_diff"].connect()
            self._register_tools(_CODE_DIFF_TOOLS)
        else:
            from agents.mcp_servers.code_diff.factory import create_code_diff_provider
            self._local_code_diff_provider = create_code_diff_provider(self._config)
            self._register_tools(_CODE_DIFF_TOOLS)

        # 4. Repo Intelligence: Remote GitHub MCP or local
        if self._config.REPO_INTELLIGENCE_BACKEND == "github_mcp":
            headers = {}
            if self._config.GITHUB_TOKEN:
                headers["Authorization"] = f"Bearer {self._config.GITHUB_TOKEN}"
            self._remote_servers["repo_intelligence"] = RemoteServerEndpoint(
                name="repo_intelligence",
                url=self._config.GITHUB_MCP_URL,
                headers=headers,
                timeout=float(self._config.TOOL_TIMEOUT_SECONDS),
            )
            await self._remote_servers["repo_intelligence"].connect()
            self._register_tools(_REPO_INTELLIGENCE_TOOLS)
        else:
            from agents.mcp_servers.repo_intelligence.factory import (
                create_repo_intelligence_provider,
            )
            self._local_repo_intelligence_provider = create_repo_intelligence_provider(self._config)
            self._register_tools(_REPO_INTELLIGENCE_TOOLS)

        # 5. Incident Knowledge: Local provider
        from agents.mcp_servers.incident_knowledge.factory import (
            create_incident_knowledge_provider,
        )
        self._local_incident_knowledge_provider = create_incident_knowledge_provider(self._config)
        self._register_tools(_INCIDENT_KNOWLEDGE_TOOLS)

        # 6. Neo4j Aura Remote MCP (if URL configured)
        if self._config.NEO4J_MCP_URL:
            neo4j_headers = {}
            if self._config.NEO4J_MCP_TOKEN:
                neo4j_headers["Authorization"] = f"Bearer {self._config.NEO4J_MCP_TOKEN}"
            self._remote_servers["neo4j"] = RemoteServerEndpoint(
                name="neo4j",
                url=self._config.NEO4J_MCP_URL,
                headers=neo4j_headers,
                timeout=float(self._config.TOOL_TIMEOUT_SECONDS),
            )
            await self._remote_servers["neo4j"].connect()
            self._register_tools(_NEO4J_REMOTE_TOOLS)

        self._initialized = True
        logger.info(
            "RemoteMCPClient ready. Remote servers: %s. Local servers: %s",
            list(self._remote_servers.keys()),
            [s for s in self._tools if s not in self._remote_servers],
        )

    def list_tools(self, server: Optional[str] = None) -> list[ToolDef]:
        """Return available tools across all servers."""
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
        """Route tool invocation to remote MCP server or local provider."""
        self._ensure_initialized()

        if server not in self._tools:
            raise KeyError(
                f"Unknown MCP server '{server}'. Available: {list(self._tools.keys())}"
            )
        if tool_name not in self._tools[server]:
            raise KeyError(
                f"Unknown tool '{tool_name}' on server '{server}'. "
                f"Available: {list(self._tools[server].keys())}"
            )

        timeout = self._config.TOOL_TIMEOUT_SECONDS

        # 1. Route to remote MCP server if configured
        if server in self._remote_servers:
            endpoint = self._remote_servers[server]
            try:
                return await asyncio.wait_for(
                    endpoint.call_tool_remote(tool_name, arguments),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"Tool {server}.{tool_name} timed out after {timeout}s")

        # 2. Otherwise route to local fallback provider
        provider = self._get_local_provider(server)
        method = getattr(provider, tool_name, None)
        if method is None:
            raise KeyError(f"Local provider for '{server}' has no method '{tool_name}'")

        try:
            return await asyncio.wait_for(method(**arguments), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Tool {server}.{tool_name} timed out after {timeout}s")

    async def shutdown(self) -> None:
        """Disconnect all remote servers and close local providers."""
        logger.info("Shutting down RemoteMCPClient...")
        for endpoint in self._remote_servers.values():
            await endpoint.disconnect()
        self._remote_servers.clear()

        if self._local_code_diff_provider and hasattr(self._local_code_diff_provider, "close"):
            await self._local_code_diff_provider.close()
        if self._local_deploy_provider and hasattr(self._local_deploy_provider, "close"):
            await self._local_deploy_provider.close()
        if self._local_repo_intelligence_provider and hasattr(
            self._local_repo_intelligence_provider, "close"
        ):
            await self._local_repo_intelligence_provider.close()

        self._local_observability_provider = None
        self._local_incident_knowledge_provider = None
        self._local_code_diff_provider = None
        self._local_deploy_provider = None
        self._local_repo_intelligence_provider = None
        self._tools.clear()
        self._initialized = False

    def _register_tools(self, tools: list[ToolDef]) -> None:
        """Add tools to registry."""
        for tool in tools:
            if tool.server not in self._tools:
                self._tools[tool.server] = {}
            self._tools[tool.server][tool.name] = tool

    def _get_local_provider(self, server: str) -> Any:
        """Get local provider instance."""
        providers = {
            "observability": self._local_observability_provider,
            "deploy": self._local_deploy_provider,
            "incident_knowledge": self._local_incident_knowledge_provider,
            "code_diff": self._local_code_diff_provider,
            "repo_intelligence": self._local_repo_intelligence_provider,
        }
        provider = providers.get(server)
        if provider is None:
            raise KeyError(f"No local provider registered for server '{server}'")
        return provider

    def _ensure_initialized(self) -> None:
        """Verify initialize() was called."""
        if not self._initialized:
            raise RuntimeError(
                "RemoteMCPClient not initialized. Call await client.initialize() first."
            )
