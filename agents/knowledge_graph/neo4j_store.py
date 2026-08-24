"""
Neo4j knowledge graph store for production.

Uses Cypher queries and native read/write transactions for ACID graph operations.
"""

import logging
from typing import Any, Optional, LiteralString

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
    #
    # Neo4j async driver results must be consumed INSIDE the
    # execute_read/execute_write transaction function, since the
    # transaction is closed once the callback returns.

    async def get_service_info(self, service_id: str) -> dict[str, Any]:
        """Fetch node metadata for service."""
        async def _read(tx: Any) -> dict[str, Any]:
            result = await tx.run(
                "MATCH (s:Service {id: $service_id}) RETURN s",
                service_id=service_id,
            )
            record = await result.single()
            if not record:
                raise KeyError(
                    f"Service '{service_id}' not found in Neo4j graph"
                )
            return dict(record["s"])

        async with self._driver.session() as session:
            return await session.execute_read(_read)

    async def get_dependencies(self, service_id: str) -> list[str]:
        """Fetch downstream dependencies (s)-[:DEPENDS_ON]->(d)."""
        async def _read(tx: Any) -> list[str]:
            result = await tx.run(
                "MATCH (s:Service {id: $service_id})-[:DEPENDS_ON]->(d) RETURN d.id AS id",
                service_id=service_id,
            )
            records = await result.data()
            return [r["id"] for r in records if "id" in r]

        async with self._driver.session() as session:
            return await session.execute_read(_read)

    async def get_dependents(self, service_id: str) -> list[str]:
        """Fetch upstream dependents (u)-[:DEPENDS_ON]->(s)."""
        async def _read(tx: Any) -> list[str]:
            result = await tx.run(
                "MATCH (u:Service)-[:DEPENDS_ON]->(s:Service {id: $service_id}) RETURN u.id AS id",
                service_id=service_id,
            )
            records = await result.data()
            return [r["id"] for r in records if "id" in r]

        async with self._driver.session() as session:
            return await session.execute_read(_read)

    async def get_blast_radius(self, service_id: str) -> list[str]:
        """Fetch service itself and all transitive upstream dependents."""
        async def _read(tx: Any) -> list[str]:
            result = await tx.run(
                "MATCH (s:Service {id: $service_id})<-[:DEPENDS_ON*0..]-(u:Service) RETURN DISTINCT u.id AS id",
                service_id=service_id,
            )
            records = await result.data()
            return sorted([r["id"] for r in records if "id" in r])

        async with self._driver.session() as session:
            return await session.execute_read(_read)

    async def get_owner_team(self, service_id: str) -> dict[str, str]:
        """Fetch owner team node."""
        async def _read(tx: Any) -> Optional[dict[str, Any]]:
            result = await tx.run(
                "MATCH (s:Service {id: $service_id})-[:OWNED_BY]->(t:Team) RETURN t",
                service_id=service_id,
            )
            record = await result.single()
            return dict(record["t"]) if record else None

        async with self._driver.session() as session:
            record = await session.execute_read(_read)
            if record:
                return record
            # Fallback to property check
            svc = await self.get_service_info(service_id)
            return {"id": svc.get("owner_team", "unknown"), "oncall_slack": "unknown"}

    async def get_historical_incidents(self, service_id: str) -> list[dict[str, Any]]:
        """Fetch past incidents attached to service."""
        async def _read(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(
                "MATCH (s:Service {id: $service_id})<-[:AFFECTED]-(i:Incident) RETURN i",
                service_id=service_id,
            )
            records = await result.data()
            return [r["i"] for r in records if "i" in r]

        async with self._driver.session() as session:
            return await session.execute_read(_read)

    async def get_all_services(self) -> list[str]:
        """Fetch all Service node IDs."""
        async def _read(tx: Any) -> list[str]:
            result = await tx.run("MATCH (s:Service) RETURN s.id AS id")
            records = await result.data()
            return sorted([r["id"] for r in records if "id" in r])

        async with self._driver.session() as session:
            return await session.execute_read(_read)

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

    async def remove_node(self, node_id: str) -> None:
        """Delete a Service node and all incident edges in Neo4j."""
        async with self._driver.session() as session:
            await session.execute_write(
                lambda tx: tx.run(
                    "MATCH (s:Service {id: $node_id}) DETACH DELETE s",
                    node_id=node_id,
                )
            )

    async def update_metadata(self, node_id: str, field: str, value: Any) -> None:
        """Update property on node."""
        async with self._driver.session() as session:
            await session.execute_write(
                lambda tx: tx.run(
                    "MATCH (s:Service {id: $node_id}) "
                    "SET s = s + $props",
                    node_id=node_id,
                    props={field: value},
                )
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
                elif action == "remove_node":
                    await self.remove_node(m["node"])
                elif action == "update_metadata":
                    await self.update_metadata(m["node"], m["field"], m["value"])
                applied += 1
            except Exception as e:
                logger.error("Failed to apply mutation %s: %s", m, e)
                errors.append(str(e))

        return {"applied": applied, "errors": errors}

    # ── Staging Methods (KG bootstrap loop) ──────────────
    #
    # Staging uses dedicated labels (:StagingService) and relationship
    # type (:STAGING_DEPENDS_ON) so it is fully isolated from the active
    # graph and works on Neo4j Community edition (single database).

    async def staging_has_content(self) -> bool:
        """True when the staging graph holds any nodes or edges."""
        async def _read(tx: Any) -> bool:
            result = await tx.run(
                "MATCH (s:StagingService) RETURN count(s) AS c "
                "UNION ALL "
                "MATCH ()-[r:STAGING_DEPENDS_ON]->() RETURN count(r) AS c "
                "UNION ALL "
                "MATCH ()-[r:STAGING_CONTAINS]->() RETURN count(r) AS c"
            )
            records = await result.data()
            return any(r["c"] > 0 for r in records if "c" in r)

        async with self._driver.session() as session:
            return await session.execute_read(_read)

    async def _staging_apply_mutations(
        self, mutations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply mutations to the staging graph."""
        applied = 0
        errors: list[str] = []
        for m in mutations:
            action = m.get("action")
            try:
                if action == "add_node":
                    props = dict(m.get("metadata", {}))
                    props["id"] = m["node"]
                    await self._run_write(
                        "MERGE (s:StagingService {id: $node_id}) SET s += $props",
                        node_id=m["node"],
                        props=props,
                    )
                elif action == "add_dependency":
                    await self._run_write(
                        "MERGE (a:StagingService {id: $from_id}) "
                        "MERGE (b:StagingService {id: $to_id}) "
                        "MERGE (a)-[:STAGING_DEPENDS_ON]->(b)",
                        from_id=m["from"],
                        to_id=m["to"],
                    )
                elif action == "remove_dependency":
                    await self._run_write(
                        "MATCH (a:StagingService {id: $from_id})"
                        "-[r:STAGING_DEPENDS_ON]->"
                        "(b:StagingService {id: $to_id}) DELETE r",
                        from_id=m["from"],
                        to_id=m["to"],
                    )
                elif action == "remove_node":
                    await self._run_write(
                        "MATCH (s:StagingService {id: $node_id}) "
                        "DETACH DELETE s",
                        node_id=m["node"],
                    )
                elif action == "update_metadata":
                    props = {m['field']: m['value']}
                    await self._run_write(
                        "MATCH (s:StagingService {id: $node_id}) "
                        "SET s = s + $props",
                        node_id=m["node"],
                        props=props,
                    )
                elif action == "add_contains":
                    await self._run_write(
                        "MERGE (a:StagingService {id: $from_id}) "
                        "MERGE (b:StagingService {id: $to_id}) "
                        "MERGE (a)-[:STAGING_CONTAINS]->(b)",
                        from_id=m["from"],
                        to_id=m["to"],
                    )
                applied += 1
            except Exception as e:
                logger.error("Failed staging mutation %s: %s", m, e)
                errors.append(str(e))
        return {"applied": applied, "errors": errors}

    async def _run_write(self, query: LiteralString, **params: Any) -> None:
        """Run a write query in a managed session."""
        async with self._driver.session() as session:
            await session.execute_write(
                lambda tx: tx.run(query, **params)  # type: ignore[arg-type]
            )

    async def staging_replace(
        self, mutations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Replace the staging graph by applying *mutations* to a clean slate."""
        await self.staging_clear()
        return await self._staging_apply_mutations(mutations)

    async def staging_apply(
        self, mutations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply *mutations* on top of the current staging graph."""
        return await self._staging_apply_mutations(mutations)

    async def staging_clear(self) -> None:
        """Remove all staged nodes and edges."""
        async with self._driver.session() as session:
            await session.execute_write(
                lambda tx: tx.run("MATCH (s:StagingService) DETACH DELETE s")
            )

    async def staging_snapshot(self) -> dict[str, Any]:
        """Return the current staging graph for visualization."""
        async def _read_nodes(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(
                "MATCH (s:StagingService) RETURN s.id AS id, s"
            )
            records = await result.data()
            return [
                {
                    "id": r["id"],
                    "kind": dict(r["s"]).get("kind", "service"),
                    "properties": dict(r["s"]),
                }
                for r in records if "id" in r
            ]

        async def _read_edges(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(
                "MATCH (a:StagingService)-[r:STAGING_DEPENDS_ON]->(b:StagingService) "
                "RETURN a.id AS from_id, b.id AS to_id, 'DEPENDS_ON' AS rel_type"
            )
            records = await result.data()
            edges = [
                {
                    "from": r["from_id"], "to": r["to_id"],
                    "type": r["rel_type"], "evidence": "staged",
                }
                for r in records if "from_id" in r
            ]
            return edges

        async def _read_contains(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(
                "MATCH (a:StagingService)-[r:STAGING_CONTAINS]->(b:StagingService) "
                "RETURN a.id AS from_id, b.id AS to_id"
            )
            records = await result.data()
            return [
                {
                    "from": r["from_id"], "to": r["to_id"],
                    "type": "CONTAINS", "evidence": "staged",
                }
                for r in records if "from_id" in r
            ]

        async with self._driver.session() as session:
            nodes = await session.execute_read(_read_nodes)
            edges = await session.execute_read(_read_edges)
            contains = await session.execute_read(_read_contains)
            return {
                "nodes": nodes,
                "edges": edges + contains,
            }

    async def active_snapshot(self) -> dict[str, Any]:
        """Return the current active graph for visualization."""
        async def _read_nodes(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(
                "MATCH (s:Service) RETURN s.id AS id, s"
            )
            records = await result.data()
            return [
                {
                    "id": r["id"],
                    "kind": dict(r["s"]).get("kind", "service"),
                    "properties": dict(r["s"]),
                }
                for r in records if "id" in r
            ]

        async def _read_edges(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(
                "MATCH (a:Service)-[r:DEPENDS_ON]->(b:Service) "
                "RETURN a.id AS from_id, b.id AS to_id, 'DEPENDS_ON' AS rel_type"
            )
            records = await result.data()
            edges = [
                {
                    "from": r["from_id"], "to": r["to_id"],
                    "type": r["rel_type"], "evidence": "active",
                }
                for r in records if "from_id" in r
            ]
            return edges

        async def _read_contains(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(
                "MATCH (a:Service)-[r:CONTAINS]->(b:Service) "
                "RETURN a.id AS from_id, b.id AS to_id"
            )
            records = await result.data()
            return [
                {
                    "from": r["from_id"], "to": r["to_id"],
                    "type": "CONTAINS", "evidence": "active",
                }
                for r in records if "from_id" in r
            ]

        async with self._driver.session() as session:
            nodes = await session.execute_read(_read_nodes)
            edges = await session.execute_read(_read_edges)
            contains = await session.execute_read(_read_contains)
            return {
                "nodes": nodes,
                "edges": edges + contains,
            }


    async def promote_staging(self) -> dict[str, Any]:
        """Apply the staged graph into the active graph and clear staging."""
        async def _promote_nodes(tx: Any) -> None:
            """Pass 1: copy staged nodes into active :Service nodes."""
            await tx.run(
                "MATCH (s:StagingService) "
                "MERGE (a:Service {id: s.id}) "
                "SET a += properties(s)"
            )

        async def _promote_depends(tx: Any) -> None:
            """Pass 2: copy staged DEPENDS_ON edges."""
            await tx.run(
                "MATCH (s:StagingService)"
                "-[:STAGING_DEPENDS_ON]->"
                "(t:StagingService) "
                "MATCH (a:Service {id: s.id}) "
                "MATCH (b:Service {id: t.id}) "
                "MERGE (a)-[:DEPENDS_ON]->(b)"
            )

        async def _promote_contains(tx: Any) -> None:
            """Pass 3: copy staged CONTAINS edges."""
            await tx.run(
                "MATCH (s:StagingService)"
                "-[:STAGING_CONTAINS]->"
                "(t:StagingService) "
                "MATCH (a:Service {id: s.id}) "
                "MATCH (b:Service {id: t.id}) "
                "MERGE (a)-[:CONTAINS]->(b)"
            )

        async def _clear(tx: Any) -> None:
            await tx.run("MATCH (s:StagingService) DETACH DELETE s")

        async with self._driver.session() as session:
            await session.execute_write(_promote_nodes)
            await session.execute_write(_promote_depends)
            await session.execute_write(_promote_contains)
            await session.execute_write(_clear)
            return {"applied": 0, "errors": []}

