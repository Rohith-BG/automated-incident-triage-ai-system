"""
Neo4j Aura Remote MCP Knowledge Graph Store.

Implements the KnowledgeGraphStore protocol by executing Cypher queries exclusively
through the official Neo4j Aura MCP server's `read-cypher` and `write-cypher` tools
(https://<INSTANCE_ID>.mcp-instances.neo4j.io).

All graph data originates from the actual remote Neo4j Aura MCP endpoint.
"""

import logging
from typing import Any, Optional

import httpx

from agents.config import AgentSettings
from agents.knowledge_graph.base import KnowledgeGraphStore

logger = logging.getLogger(__name__)


class Neo4jMCPStore:
    """KnowledgeGraphStore adapter executing Cypher via official Neo4j Aura MCP tools."""

    def __init__(
        self,
        config: AgentSettings,
        mcp_client: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._url = config.NEO4J_MCP_URL or ""
        self._token = config.NEO4J_MCP_TOKEN
        self._mcp_client = mcp_client
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or initialize HTTP client."""
        if self._http_client is None:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._http_client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self._config.TOOL_TIMEOUT_SECONDS),
            )
        return self._http_client

    async def _execute_cypher(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
        is_write: bool = False,
    ) -> list[dict[str, Any]]:
        """Execute Cypher via official Aura MCP read-cypher or write-cypher tool."""
        tool_name = "write-cypher" if is_write else "read-cypher"
        arguments = {"query": query, "params": params or {}}

        # If an MCPClient was provided, route via client
        if self._mcp_client is not None:
            res = await self._mcp_client.call_tool("neo4j", tool_name, arguments)
            return self._parse_mcp_result(res)

        # Otherwise execute directly against configured Aura MCP endpoint
        if not self._url:
            raise ValueError(
                "NEO4J_MCP_URL is not configured. Set NEO4J_MCP_URL=https://<INSTANCE_ID>.mcp-instances.neo4j.io"
            )

        client = await self._get_http_client()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        resp = await client.post(self._url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"Neo4j Aura MCP Error on {tool_name}: {data['error']}")

        return self._parse_mcp_result(data.get("result", {}))

    def _parse_mcp_result(self, result: Any) -> list[dict[str, Any]]:
        """Normalize Neo4j MCP response records."""
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            # Neo4j MCP typically returns {"results": [...]} or {"rows": [...]} or content blocks
            if "results" in result and isinstance(result["results"], list):
                return result["results"]
            if "rows" in result and isinstance(result["rows"], list):
                return result["rows"]
            if "content" in result and isinstance(result["content"], list):
                extracted = []
                for item in result["content"]:
                    if isinstance(item, dict) and "text" in item:
                        extracted.append(item["text"])
                    else:
                        extracted.append(item)
                return extracted
        return []

    # ── Read Query Methods ─────────────────────────────────

    async def get_service_info(self, service_id: str) -> dict[str, Any]:
        """Fetch node metadata for service via Aura MCP read-cypher."""
        query = "MATCH (s:Service {id: $service_id}) RETURN s"
        records = await self._execute_cypher(query, {"service_id": service_id})
        if not records:
            raise KeyError(f"Service '{service_id}' not found in Neo4j Aura graph")
        first = records[0]
        return dict(first.get("s", first))

    async def get_dependencies(self, service_id: str) -> list[str]:
        """Fetch downstream dependencies via Aura MCP read-cypher."""
        query = (
            "MATCH (s:Service {id: $service_id})-[:DEPENDS_ON]->(d) "
            "RETURN d.id AS id"
        )
        records = await self._execute_cypher(query, {"service_id": service_id})
        deps = []
        for r in records:
            if isinstance(r, dict) and "id" in r:
                deps.append(r["id"])
            elif isinstance(r, str):
                deps.append(r)
        return deps

    async def get_dependents(self, service_id: str) -> list[str]:
        """Fetch upstream dependents via Aura MCP read-cypher."""
        query = (
            "MATCH (u:Service)-[:DEPENDS_ON]->(s:Service {id: $service_id}) "
            "RETURN u.id AS id"
        )
        records = await self._execute_cypher(query, {"service_id": service_id})
        dependents = []
        for r in records:
            if isinstance(r, dict) and "id" in r:
                dependents.append(r["id"])
            elif isinstance(r, str):
                dependents.append(r)
        return dependents

    async def get_blast_radius(self, service_id: str) -> list[str]:
        """Fetch full blast radius via Aura MCP read-cypher."""
        query = (
            "MATCH (s:Service {id: $service_id})<-[:DEPENDS_ON*0..]-(u:Service) "
            "RETURN DISTINCT u.id AS id"
        )
        records = await self._execute_cypher(query, {"service_id": service_id})
        blast = []
        for r in records:
            if isinstance(r, dict) and "id" in r:
                blast.append(r["id"])
            elif isinstance(r, str):
                blast.append(r)
        return sorted(blast)

    async def get_historical_incidents(
        self, service_id: str
    ) -> list[dict[str, Any]]:
        """Fetch resolved incidents for service from backend DB."""
        try:
            from backend.app.repositories.incident import (
                IncidentRepository,
            )
            from backend.app.core.database import async_session_factory

            async with async_session_factory() as session:
                repo = IncidentRepository(session)
                incidents = await repo.find_resolved_by_service(
                    service_id, limit=10
                )
                return [
                    {
                        "id": str(inc.id),
                        "service_id": inc.service_id,
                        "status": inc.status,
                        "root_cause": (
                            inc.report.root_cause
                            if inc.report
                            else None
                        ),
                        "resolved_at": inc.updated_at.isoformat(),
                    }
                    for inc in incidents
                ]
        except Exception as e:
            logger.warning(
                "Failed to fetch historical incidents for %s: %s",
                service_id, e,
            )
            return []

    async def get_all_services(self) -> list[str]:
        """Fetch all Service node IDs via Aura MCP read-cypher."""
        query = "MATCH (s:Service) RETURN s.id AS id"
        records = await self._execute_cypher(query)
        services = []
        for r in records:
            if isinstance(r, dict) and "id" in r:
                services.append(r["id"])
            elif isinstance(r, str):
                services.append(r)
        return sorted(services)

    async def get_repo_for_service(self, service_id: str) -> str:
        """Fetch repo property for service."""
        try:
            svc = await self.get_service_info(service_id)
            return svc.get("repo", "")
        except KeyError:
            return ""

    # ── Write Mutation Methods ─────────────────────────────

    async def apply_mutations(
        self, mutations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply batch mutations via Aura MCP write-cypher."""
        applied = 0
        for m in mutations:
            action = m.get("action")
            if action == "add_dependency":
                await self.add_dependency(m["from"], m["to"])
                applied += 1
            elif action == "remove_dependency":
                await self.remove_dependency(m["from"], m["to"])
                applied += 1
            elif action == "add_node":
                await self.add_node(m.get("node_id") or m.get("id", ""), m.get("metadata", {}))
                applied += 1
            elif action == "remove_node":
                await self.remove_node(m.get("node_id") or m.get("id", ""))
                applied += 1
        return {"applied": applied, "errors": []}

    async def add_dependency(self, from_id: str, to_id: str) -> None:
        """Add dependency edge via Aura MCP write-cypher."""
        query = (
            "MATCH (f:Service {id: $from_id}), (t:Service {id: $to_id}) "
            "MERGE (f)-[:DEPENDS_ON]->(t)"
        )
        await self._execute_cypher(query, {"from_id": from_id, "to_id": to_id}, is_write=True)

    async def remove_dependency(self, from_id: str, to_id: str) -> None:
        """Remove dependency edge via Aura MCP write-cypher."""
        query = (
            "MATCH (f:Service {id: $from_id})-[r:DEPENDS_ON]->(t:Service {id: $to_id}) "
            "DELETE r"
        )
        await self._execute_cypher(query, {"from_id": from_id, "to_id": to_id}, is_write=True)

    async def add_node(self, node_id: str, metadata: dict[str, Any]) -> None:
        """Add or update Service node via Aura MCP write-cypher."""
        props = dict(metadata)
        props["id"] = node_id
        query = "MERGE (s:Service {id: $id}) SET s += $props"
        await self._execute_cypher(query, {"id": node_id, "props": props}, is_write=True)

    async def remove_node(self, node_id: str) -> None:
        """Remove Service node via Aura MCP write-cypher."""
        query = "MATCH (s:Service {id: $id}) DETACH DELETE s"
        await self._execute_cypher(query, {"id": node_id}, is_write=True)

    async def update_metadata(self, node_id: str, field: str, value: Any) -> None:
        """Update property on Service node via Aura MCP write-cypher."""
        query = f"MATCH (s:Service {{id: $id}}) SET s.{field} = $val"
        await self._execute_cypher(query, {"id": node_id, "val": value}, is_write=True)

    # ── Staging Methods ────────────────────────────────────

    async def staging_has_content(self) -> bool:
        """True when staging nodes exist."""
        query = "MATCH (s:StagingService) RETURN count(s) AS count"
        records = await self._execute_cypher(query)
        if records and isinstance(records[0], dict):
            return records[0].get("count", 0) > 0
        return False

    async def staging_replace(
        self, mutations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Replace staging graph."""
        await self.staging_clear()
        return await self.staging_apply(mutations)

    async def staging_apply(
        self, mutations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply mutations onto staging graph."""
        applied = 0
        for m in mutations:
            action = m.get("action")
            if action in ("add_node", "create_service"):
                node_id = m.get("node_id") or m.get("id", "")
                props = dict(m.get("properties") or m.get("metadata", {}))
                props["id"] = node_id
                query = "MERGE (s:StagingService {id: $id}) SET s += $props"
                await self._execute_cypher(query, {"id": node_id, "props": props}, is_write=True)
                applied += 1
            elif action in ("add_dependency", "add_edge"):
                query = (
                    "MATCH (f:StagingService {id: $from_id}), (t:StagingService {id: $to_id}) "
                    "MERGE (f)-[:STAGING_DEPENDS_ON]->(t)"
                )
                await self._execute_cypher(
                    query, {"from_id": m["from"], "to_id": m["to"]}, is_write=True
                )
                applied += 1
        return {"applied": applied, "errors": []}

    async def staging_clear(self) -> None:
        """Clear staging graph."""
        query = "MATCH (s:StagingService) DETACH DELETE s"
        await self._execute_cypher(query, is_write=True)

    async def staging_snapshot(self) -> dict[str, Any]:
        """Return snapshot of staged graph."""
        nodes_q = "MATCH (s:StagingService) RETURN s.id AS id, properties(s) AS props"
        edges_q = "MATCH (f:StagingService)-[:STAGING_DEPENDS_ON]->(t:StagingService) RETURN f.id AS from_id, t.id AS to_id"
        nodes = await self._execute_cypher(nodes_q)
        edges = await self._execute_cypher(edges_q)
        return {
            "nodes": [{"id": n.get("id"), "kind": "service", "properties": n.get("props", {})} for n in nodes if isinstance(n, dict)],
            "edges": [{"from": e.get("from_id"), "to": e.get("to_id"), "type": "depends_on"} for e in edges if isinstance(e, dict)],
        }

    async def active_snapshot(self) -> dict[str, Any]:
        """Return snapshot of active graph."""
        nodes_q = "MATCH (s:Service) RETURN s.id AS id, properties(s) AS props"
        edges_q = "MATCH (f:Service)-[:DEPENDS_ON]->(t:Service) RETURN f.id AS from_id, t.id AS to_id"
        nodes = await self._execute_cypher(nodes_q)
        edges = await self._execute_cypher(edges_q)
        return {
            "nodes": [{"id": n.get("id"), "kind": "service", "properties": n.get("props", {})} for n in nodes if isinstance(n, dict)],
            "edges": [{"from": e.get("from_id"), "to": e.get("to_id"), "type": "depends_on"} for e in edges if isinstance(e, dict)],
        }

    async def promote_staging(self) -> dict[str, Any]:
        """Promote staging graph into active Service nodes."""
        query_nodes = (
            "MATCH (s:StagingService) "
            "MERGE (a:Service {id: s.id}) "
            "SET a += properties(s)"
        )
        await self._execute_cypher(query_nodes, is_write=True)
        query_edges = (
            "MATCH (f:StagingService)-[:STAGING_DEPENDS_ON]->(t:StagingService) "
            "MATCH (af:Service {id: f.id}), (at:Service {id: t.id}) "
            "MERGE (af)-[:DEPENDS_ON]->(at)"
        )
        await self._execute_cypher(query_edges, is_write=True)
        await self.staging_clear()
        return {"status": "promoted", "errors": []}

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
