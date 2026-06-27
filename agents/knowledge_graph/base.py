"""
Protocol interface for the knowledge graph store.

Every implementation (in-memory, Neo4j, etc.) must satisfy
this contract. Consumers depend only on this Protocol —
never on a concrete class.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class KnowledgeGraphStore(Protocol):
    """Read-only knowledge graph used by the orchestrator."""

    async def get_service_info(
        self, service_id: str
    ) -> dict[str, Any]:
        """Return full metadata for a single service.

        Keys: id, owner_team, dependencies, repo, language,
              alert_threshold.
        Raises KeyError if service not found.
        """
        ...

    async def get_dependencies(
        self, service_id: str
    ) -> list[str]:
        """Return direct downstream dependency IDs."""
        ...

    async def get_dependents(
        self, service_id: str
    ) -> list[str]:
        """Return services that depend on this service (upstream)."""
        ...

    async def get_blast_radius(
        self, service_id: str
    ) -> list[str]:
        """Return full blast radius: the service itself +
        all transitive upstream dependents.

        Used to scope log/metrics collection before
        parallel investigation.
        """
        ...

    async def get_owner_team(
        self, service_id: str
    ) -> dict[str, str]:
        """Return owner team info including oncall_slack channel.

        Returns: {"id": "...", "oncall_slack": "#..."}
        """
        ...

    async def get_historical_incidents(
        self, service_id: str
    ) -> list[dict[str, Any]]:
        """Return past incidents for this service.

        MVP: returns empty list (no history stored yet).
        Prod: queries incident DB or Neo4j relationships.
        """
        ...

    async def get_all_services(self) -> list[str]:
        """Return all known service IDs."""
        ...

    async def get_repo_for_service(
        self, service_id: str
    ) -> str:
        """Return the GitHub repo slug (org/repo) for a service."""
        ...
