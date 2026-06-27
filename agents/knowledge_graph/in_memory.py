"""
In-memory knowledge graph implementation.

Loads `data/services.json` at init and builds a dict-based
graph. Used for MVP / dev mode. Swap to Neo4j by changing
KG_BACKEND env var — zero code change in consumers.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


class InMemoryGraphStore:
    """Dict-based knowledge graph backed by services.json."""

    def __init__(self, services_json_path: Path) -> None:
        """Load and index the services graph.

        Args:
            services_json_path: Absolute path to services.json.
        """
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

        # Build reverse dependency index:
        # dependents_map[X] = list of services that depend on X
        self._dependents_map: dict[str, list[str]] = defaultdict(
            list
        )
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
        """BFS upward: service + all transitive dependents.

        Example: if payment-service is down →
          checkout-service depends on it →
          frontend depends on checkout-service →
          blast radius = [payment-service, checkout-service,
                          frontend, load-generator]
        """
        visited: set[str] = set()
        queue: list[str] = [service_id]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            # Only traverse upward through known services
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
