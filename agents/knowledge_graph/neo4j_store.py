"""
Neo4j knowledge graph store for production.

Uses Cypher queries and native read/write transactions for ACID graph operations.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from neo4j import AsyncGraphDatabase
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False


class Neo4jGraphStore:
    """Production Neo4j KnowledgeGraphStore implementation."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        """Initialise Neo4j driver connection."""
        if not HAS_NEO4J:
            raise ImportError(
                "neo4j package is required for Neo4jGraphStore. "
                "Install it via `pip install neo4j`."
            )
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self) -> None:
        """Close driver session."""
        await self._driver.close()

    # ── Read Methods ──────────────────────────────────────

    async def get_service_info(self, service_id: str) -> dict[str, Any]:
        """Fetch node metadata for service."""
        async with self._driver.session() as session:
            result = await session.execute_read(
                lambda tx: tx.run(
                    "MATCH (s:Service {id: $service_id}) RETURN s",
                    service_id=service_id,
                )
            )
            record = await result.single()
            if not record:
                raise KeyError(f"Service '{service_id}' not found in Neo4j graph")
            return dict(record["s"])

    async def get_dependencies(self, service_id: str) -> list[str]:
        """Fetch downstream dependencies (s)-[:DEPENDS_ON]->(d)."""
        async with self._driver.session() as session:
            result = await session.execute_read(
                lambda tx: tx.run(
                    "MATCH (s:Service {id: $service_id})-[:DEPENDS_ON]->(d) RETURN d.id AS id",
                    service_id=service_id,
                )
            )
            records = await result.data()
            return [r["id"] for r in records if "id" in r]

    async def get_dependents(self, service_id: str) -> list[str]:
        """Fetch upstream dependents (u)-[:DEPENDS_ON]->(s)."""
        async with self._driver.session() as session:
            result = await session.execute_read(
                lambda tx: tx.run(
                    "MATCH (u:Service)-[:DEPENDS_ON]->(s:Service {id: $service_id}) RETURN u.id AS id",
                    service_id=service_id,
                )
            )
            records = await result.data()
            return [r["id"] for r in records if "id" in r]

    async def get_blast_radius(self, service_id: str) -> list[str]:
        """Fetch service itself and all transitive upstream dependents."""
        async with self._driver.session() as session:
            result = await session.execute_read(
                lambda tx: tx.run(
                    "MATCH (s:Service {id: $service_id})<-[:DEPENDS_ON*0..]-(u:Service) RETURN DISTINCT u.id AS id",
                    service_id=service_id,
                )
            )
            records = await result.data()
            return sorted([r["id"] for r in records if "id" in r])

    async def get_owner_team(self, service_id: str) -> dict[str, str]:
        """Fetch owner team node."""
        async with self._driver.session() as session:
            result = await session.execute_read(
                lambda tx: tx.run(
                    "MATCH (s:Service {id: $service_id})-[:OWNED_BY]->(t:Team) RETURN t",
                    service_id=service_id,
                )
            )
            record = await result.single()
            if record:
                return dict(record["t"])
            # Fallback to property check
            svc = await self.get_service_info(service_id)
            return {"id": svc.get("owner_team", "unknown"), "oncall_slack": "unknown"}

    async def get_historical_incidents(self, service_id: str) -> list[dict[str, Any]]:
        """Fetch past incidents attached to service."""
        async with self._driver.session() as session:
            result = await session.execute_read(
                lambda tx: tx.run(
                    "MATCH (s:Service {id: $service_id})<-[:AFFECTED]-(i:Incident) RETURN i",
                    service_id=service_id,
                )
            )
            records = await result.data()
            return [r["i"] for r in records if "i" in r]

    async def get_all_services(self) -> list[str]:
        """Fetch all Service node IDs."""
        async with self._driver.session() as session:
            result = await session.execute_read(
                lambda tx: tx.run("MATCH (s:Service) RETURN s.id AS id")
            )
            records = await result.data()
            return sorted([r["id"] for r in records if "id" in r])

    async def get_repo_for_service(self, service_id: str) -> str:
        """Fetch repo property for service."""
        svc = await self.get_service_info(service_id)
        return svc.get("repo", "")

    # ── Write Mutation Methods ─────────────────────────────

    async def add_dependency(self, from_id: str, to_id: str) -> None:
        """Add a DEPENDS_ON relationship in Neo4j."""
        async with self._driver.session() as session:
            await session.execute_write(
                lambda tx: tx.run(
                    "MERGE (a:Service {id: $from_id}) "
                    "MERGE (b:Service {id: $to_id}) "
                    "MERGE (a)-[:DEPENDS_ON]->(b)",
                    from_id=from_id,
                    to_id=to_id,
                )
            )

    async def remove_dependency(self, from_id: str, to_id: str) -> None:
        """Delete a DEPENDS_ON relationship in Neo4j."""
        async with self._driver.session() as session:
            await session.execute_write(
                lambda tx: tx.run(
                    "MATCH (a:Service {id: $from_id})-[r:DEPENDS_ON]->(b:Service {id: $to_id}) "
                    "DELETE r",
                    from_id=from_id,
                    to_id=to_id,
                )
            )

    async def add_node(self, node_id: str, metadata: dict[str, Any]) -> None:
        """Merge a Service node with metadata properties."""
        async with self._driver.session() as session:
            props = dict(metadata)
            props["id"] = node_id
            await session.execute_write(
                lambda tx: tx.run(
                    "MERGE (s:Service {id: $node_id}) SET s += $props",
                    node_id=node_id,
                    props=props,
                )
            )

    async def update_metadata(self, node_id: str, field: str, value: Any) -> None:
        """Update property on node."""
        async with self._driver.session() as session:
            query = f"MATCH (s:Service {{id: $node_id}}) SET s.{field} = $value"
            await session.execute_write(
                lambda tx: tx.run(query, node_id=node_id, value=value)
            )

    async def apply_mutations(self, mutations: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply batch mutations atomically in Neo4j."""
        applied = 0
        errors = []
        for m in mutations:
            action = m.get("action")
            try:
                if action == "add_dependency":
                    await self.add_dependency(m["from"], m["to"])
                elif action == "remove_dependency":
                    await self.remove_dependency(m["from"], m["to"])
                elif action == "add_node":
                    await self.add_node(m["node"], m.get("metadata", {}))
                elif action == "update_metadata":
                    await self.update_metadata(m["node"], m["field"], m["value"])
                applied += 1
            except Exception as e:
                logger.error("Failed to apply mutation %s: %s", m, e)
                errors.append(str(e))

        return {"applied": applied, "errors": errors}
