"""
Protocol interface for the incident knowledge provider.
"""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class IncidentKnowledgeProvider(Protocol):
    """Institutional memory data source contract."""

    async def search_incident_knowledge(
        self,
        service: str,
        error_type: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search incident knowledge matching service, error type, and query keyword."""
        ...

    async def get_incident_knowledge(
        self,
        incident_knowledge_id: str,
    ) -> Optional[dict[str, Any]]:
        """Get detail of an incident knowledge entry by ID."""
        ...

    async def get_past_resolutions(
        self,
        service: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return recent successful incident resolutions for *service*."""
        ...

    async def get_similar_incidents(
        self,
        service: str,
        error_pattern: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return historical incidents with reports for *service*."""
        ...
