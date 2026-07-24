"""
Protocol interface for the knowledge graph store.

Every implementation (in-memory, Neo4j, etc.) must satisfy
this contract. Consumers depend only on this Protocol —
never on a concrete class.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class KnowledgeGraphStore(Protocol):
    """Knowledge graph store supporting both read queries and mutation updates."""

    async def get_service_info(
        self, service_id: str
    ) -> dict[str, Any]:
        """Return full metadata for a single service."""
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
        """Return full blast radius: the service itself + all transitive upstream dependents."""
        ...

    async def get_owner_team(
        self, service_id: str
    ) -> dict[str, str]:
        """Return owner team info including oncall_slack channel."""
        ...

    async def get_historical_incidents(
        self, service_id: str
    ) -> list[dict[str, Any]]:
        """Return past incidents for this service."""
        ...

    async def get_all_services(self) -> list[str]:
        """Return all known service IDs."""
        ...

    async def get_repo_for_service(
        self, service_id: str
    ) -> str:
        """Return the GitHub repo slug (org/repo) for a service."""
        ...

    # ── Write Mutation Methods ─────────────────────────────

    async def apply_mutations(
        self, mutations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply a batch of graph mutations atomically."""
        ...

    async def add_dependency(
        self, from_id: str, to_id: str
    ) -> None:
        """Add a dependency edge from_id -> to_id."""
        ...

    async def remove_dependency(
        self, from_id: str, to_id: str
    ) -> None:
        """Remove a dependency edge from_id -> to_id."""
        ...

    async def add_node(
        self, node_id: str, metadata: dict[str, Any]
    ) -> None:
        """Add or update a service/module node."""
        ...

    async def update_metadata(
        self, node_id: str, field: str, value: Any
    ) -> None:
        """Update a metadata property on an existing node."""
        ...
