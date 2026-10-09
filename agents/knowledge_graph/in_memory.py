"""
In-memory knowledge graph implementation.

Loads `data/services.json` at init and builds a dict-based
graph. Used for MVP / dev mode. Swap to Neo4j by changing
KG_BACKEND env var — zero code change in consumers.
"""

import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


class InMemoryGraphStore:
    """Dict-based knowledge graph backed by services.json with mutation lock for dev mode."""

    def __init__(
        self,
        services_json_path: Path,
        seed_from_fixtures: bool = True,
    ) -> None:
        """Load and index the services graph.

        Args:
            services_json_path: Absolute path to services.json.
            seed_from_fixtures: When False, start with an empty graph
                (used to exercise the first-run KG bootstrap flow in dev).
        """
        self._lock = asyncio.Lock()

        if seed_from_fixtures:
            with open(services_json_path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            # Index services by ID
            self._services: dict[str, dict[str, Any]] = {
                svc["id"]: svc for svc in raw["services"]
            }

            # Index teams by ID
            self._teams: dict[str, dict[str, str]] = {
                team["id"]: team for team in raw["teams"]
            }

            # Known non-service nodes (external APIs, databases)
            self._external_apis: set[str] = set(
                raw.get("external_apis", [])
            )
            self._databases: set[str] = set(
                raw.get("databases", [])
            )
        else:
            self._services = {}
            self._teams = {}
            self._external_apis = set()
            self._databases = set()

        self._rebuild_dependents_map()

        # Staging graph for the KG bootstrap loop
        self._staging_nodes: dict[str, dict[str, Any]] = {}
        self._staging_edges: set[tuple[str, str]] = set()
        self._staging_contains_edges: set[tuple[str, str]] = set()

    def _rebuild_dependents_map(self) -> None:
        """Rebuild reverse dependency index."""
        self._dependents_map: dict[str, list[str]] = defaultdict(list)
        for svc_id, svc in self._services.items():
            for dep in svc.get("dependencies", []):
                self._dependents_map[dep].append(svc_id)

    # ── Protocol methods ─────────────────────────────────

    async def get_service_info(
        self, service_id: str
    ) -> dict[str, Any]:
        """Return full metadata for a single service."""
        if service_id not in self._services:
            raise KeyError(
                f"Service '{service_id}' not found in graph"
            )
        return dict(self._services[service_id])

    async def get_dependencies(
        self, service_id: str
    ) -> list[str]:
        """Return direct downstream dependency IDs."""
        svc = await self.get_service_info(service_id)
        return list(svc.get("dependencies", []))

    async def get_dependents(
        self, service_id: str
    ) -> list[str]:
        """Return services that depend on this service."""
        return list(self._dependents_map.get(service_id, []))

    async def get_blast_radius(
        self, service_id: str
    ) -> list[str]:
        """BFS upward: service + all transitive dependents."""
        visited: set[str] = set()
        queue: list[str] = [service_id]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for dependent in self._dependents_map.get(
                current, []
            ):
                if dependent not in visited:
                    queue.append(dependent)

        return sorted(visited)

    async def get_owner_team(
        self, service_id: str
    ) -> dict[str, str]:
        """Return owner team info with oncall_slack."""
        svc = await self.get_service_info(service_id)
        team_id = svc["owner_team"]
        if team_id not in self._teams:
            return {"id": team_id, "oncall_slack": "unknown"}
        return dict(self._teams[team_id])

    async def get_historical_incidents(
        self, service_id: str
    ) -> list[dict[str, Any]]:
        """MVP: no incident history stored yet."""
        return []

    async def get_all_services(self) -> list[str]:
        """Return all known service IDs."""
        return sorted(self._services.keys())

    async def get_repo_for_service(
        self, service_id: str
    ) -> str:
        """Return the GitHub repo slug for a service."""
        svc = await self.get_service_info(service_id)
        return svc.get("repo", "")

    # ── Write Mutation Methods ─────────────────────────────

    async def add_dependency(self, from_id: str, to_id: str) -> None:
        """Add a dependency edge from_id -> to_id."""
        async with self._lock:
            if from_id in self._services:
                deps = self._services[from_id].setdefault("dependencies", [])
                if to_id not in deps:
                    deps.append(to_id)
                self._rebuild_dependents_map()

    async def remove_dependency(self, from_id: str, to_id: str) -> None:
        """Remove a dependency edge from_id -> to_id."""
        async with self._lock:
            if from_id in self._services:
                deps = self._services[from_id].get("dependencies", [])
                if to_id in deps:
                    deps.remove(to_id)
                self._rebuild_dependents_map()

    async def add_node(self, node_id: str, metadata: dict[str, Any]) -> None:
        """Add or update a service node in dev graph."""
        async with self._lock:
            if node_id not in self._services:
                self._services[node_id] = {
                    "id": node_id,
                    "owner_team": metadata.get("owner_team", "platform-team"),
                    "dependencies": metadata.get("dependencies", []),
                    "repo": metadata.get("repo", ""),
                    "language": metadata.get("language", "Python"),
                    "alert_threshold": metadata.get("alert_threshold", "medium"),
                    "architecture_type": metadata.get("architecture_type", "microservice"),
                }
            else:
                self._services[node_id].update(metadata)
            self._rebuild_dependents_map()

    async def remove_node(self, node_id: str) -> None:
        """Remove a service node and all incident edges."""
        async with self._lock:
            if node_id in self._services:
                del self._services[node_id]
            for svc in self._services.values():
                deps = svc.get("dependencies", [])
                if node_id in deps:
                    deps.remove(node_id)
            self._external_apis.discard(node_id)
            self._databases.discard(node_id)
            self._rebuild_dependents_map()

    async def update_metadata(self, node_id: str, field: str, value: Any) -> None:
        """Update property on dev node."""
        async with self._lock:
            if node_id in self._services:
                self._services[node_id][field] = value

    async def apply_mutations(self, mutations: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply batch mutations to dev graph."""
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
                errors.append(str(e))
        return {"applied": applied, "errors": errors}

    # ── Staging Methods (KG bootstrap loop) ──────────────

    @staticmethod
    def _apply_to_scratch(
        nodes: dict[str, dict[str, Any]],
        edges: set[tuple[str, str]],
        mutation: dict[str, Any],
        contains_edges: set[tuple[str, str]] | None = None,
    ) -> None:
        """Apply a single mutation dict to a scratch (staging) graph."""
        action = mutation.get("action")
        if action == "add_node":
            node_id = mutation["node"]
            metadata = mutation.get("metadata", {})
            if node_id in nodes:
                nodes[node_id].update(metadata)
            else:
                nodes[node_id] = dict(metadata)
        elif action == "add_dependency":
            edges.add((mutation["from"], mutation["to"]))
        elif action == "add_contains":
            target = contains_edges if contains_edges is not None else edges
            target.add((mutation["from"], mutation["to"]))
        elif action == "remove_dependency":
            edges.discard((mutation["from"], mutation["to"]))
        elif action == "update_metadata":
            node_id = mutation["node"]
            if node_id in nodes:
                nodes[node_id][mutation["field"]] = mutation["value"]
        elif action == "remove_node":
            node_id = mutation["node"]
            nodes.pop(node_id, None)
            edges.difference_update(
                (src, dst)
                for src, dst in list(edges)
                if src == node_id or dst == node_id
            )
            if contains_edges is not None:
                contains_edges.difference_update(
                    (src, dst)
                    for src, dst in list(contains_edges)
                    if src == node_id or dst == node_id
                )

    async def _staging_apply_mutations(
        self, mutations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply mutations to the staging graph in memory."""
        applied = 0
        errors: list[str] = []
        for m in mutations:
            try:
                self._apply_to_scratch(
                    self._staging_nodes,
                    self._staging_edges,
                    m,
                    self._staging_contains_edges,
                )
                applied += 1
            except Exception as e:
                errors.append(str(e))
        return {"applied": applied, "errors": errors}

    async def staging_has_content(self) -> bool:
        """True when the staging graph holds any nodes or edges."""
        return (
            bool(self._staging_nodes)
            or bool(self._staging_edges)
            or bool(self._staging_contains_edges)
        )

    async def staging_replace(
        self, mutations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Replace the staging graph by applying *mutations* to a clean slate."""
        async with self._lock:
            self._staging_nodes.clear()
            self._staging_edges.clear()
            self._staging_contains_edges.clear()
            return await self._staging_apply_mutations(mutations)

    async def staging_apply(
        self, mutations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply *mutations* on top of the current staging graph."""
        async with self._lock:
            return await self._staging_apply_mutations(mutations)

    async def staging_clear(self) -> None:
        """Remove all staged nodes and edges."""
        async with self._lock:
            self._staging_nodes.clear()
            self._staging_edges.clear()
            self._staging_contains_edges.clear()

    async def staging_snapshot(self) -> dict[str, Any]:
        """Return the current staging graph for visualization."""
        async with self._lock:
            nodes = [
                {"id": node_id, "kind": props.get("kind", "service"), "properties": dict(props)}
                for node_id, props in self._staging_nodes.items()
            ]
            dep_edges = [
                {"from": src, "to": dst, "type": "DEPENDS_ON", "evidence": "staged"}
                for src, dst in sorted(self._staging_edges)
            ]
            contains_edges = [
                {"from": src, "to": dst, "type": "CONTAINS", "evidence": "staged"}
                for src, dst in sorted(self._staging_contains_edges)
            ]
            return {"nodes": nodes, "edges": dep_edges + contains_edges}

    async def active_snapshot(self) -> dict[str, Any]:
        """Return the current active graph for visualization."""
        async with self._lock:
            nodes = [
                {"id": node_id, "kind": props.get("kind", "service"), "properties": dict(props)}
                for node_id, props in self._services.items()
            ]
            edges = []
            for src, props in self._services.items():
                for dst in props.get("dependencies", []):
                    edges.append({"from": src, "to": dst, "type": "DEPENDS_ON", "evidence": "active"})
            return {"nodes": nodes, "edges": edges}


    async def promote_staging(self) -> dict[str, Any]:
        """Apply the staged graph into the active graph and clear staging."""
        async with self._lock:
            applied = 0
            errors: list[str] = []
            for node_id, props in self._staging_nodes.items():
                try:
                    self._add_node_locked(node_id, props)
                    applied += 1
                except Exception as e:
                    errors.append(str(e))
            for src, dst in self._staging_edges:
                try:
                    self._add_dependency_locked(src, dst)
                    applied += 1
                except Exception as e:
                    errors.append(str(e))
            # Contains edges are also promoted as dependency
            # links in the active graph (hierarchy).
            for src, dst in self._staging_contains_edges:
                try:
                    self._add_dependency_locked(src, dst)
                    applied += 1
                except Exception as e:
                    errors.append(str(e))
            self._rebuild_dependents_map()
            self._staging_nodes.clear()
            self._staging_edges.clear()
            self._staging_contains_edges.clear()
            return {"applied": applied, "errors": errors}

    def _add_node_locked(self, node_id: str, metadata: dict[str, Any]) -> None:
        """Add/update a service node (caller must hold the lock)."""
        if node_id not in self._services:
            self._services[node_id] = {
                "id": node_id,
                "owner_team": metadata.get("owner_team", "platform-team"),
                "dependencies": metadata.get("dependencies", []),
                "repo": metadata.get("repo", ""),
                "language": metadata.get("language", "Python"),
                "alert_threshold": metadata.get("alert_threshold", "medium"),
                "architecture_type": metadata.get("architecture_type", "microservice"),
            }
        else:
            self._services[node_id].update(metadata)

    def _add_dependency_locked(self, from_id: str, to_id: str) -> None:
        """Add a dependency edge (caller must hold the lock)."""
        if from_id in self._services:
            deps = self._services[from_id].setdefault("dependencies", [])
            if to_id not in deps:
                deps.append(to_id)
