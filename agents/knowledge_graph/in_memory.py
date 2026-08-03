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

    def __init__(self, services_json_path: Path) -> None:
        """Load and index the services graph.

        Args:
            services_json_path: Absolute path to services.json.
        """
        self._lock = asyncio.Lock()
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

        self._rebuild_dependents_map()

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
                elif action == "update_metadata":
                    await self.update_metadata(m["node"], m["field"], m["value"])
                applied += 1
            except Exception as e:
                errors.append(str(e))
        return {"applied": applied, "errors": errors}

