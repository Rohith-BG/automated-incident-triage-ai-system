"""
Repository for service registry operations.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.service_registry import ServiceRegistry


class ServiceRegistryRepository:
    """Database access for service registry."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        service_id: str,
        repo: str,
        owner_team: str,
        architecture_type: str = "microservice",
        language: Optional[str] = None,
        alert_threshold: str = "medium",
    ) -> ServiceRegistry:
        """Register a new service."""
        entry = ServiceRegistry(
            service_id=service_id,
            repo=repo,
            architecture_type=architecture_type,
            owner_team=owner_team,
            language=language,
            alert_threshold=alert_threshold,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_by_service_id(
        self, service_id: str
    ) -> Optional[ServiceRegistry]:
        """Fetch a service by its service_id."""
        stmt = select(ServiceRegistry).where(
            ServiceRegistry.service_id == service_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_repo_for_service(
        self, service_id: str
    ) -> Optional[str]:
        """Return the repo slug for a service_id, or None."""
        entry = await self.get_by_service_id(service_id)
        return entry.repo if entry else None

    async def list_all(
        self, active_only: bool = True
    ) -> list[ServiceRegistry]:
        """List all registered services."""
        stmt = select(ServiceRegistry).order_by(
            ServiceRegistry.service_id
        )
        if active_only:
            stmt = stmt.where(ServiceRegistry.is_active == True)  # noqa: E712
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        service_id: str,
        **kwargs: object,
    ) -> Optional[ServiceRegistry]:
        """Update fields on an existing service."""
        entry = await self.get_by_service_id(service_id)
        if not entry:
            return None
        for key, val in kwargs.items():
            if val is not None and hasattr(entry, key):
                setattr(entry, key, val)
        await self._session.flush()
        return entry

    async def delete(self, service_id: str) -> bool:
        """Soft-delete a service by marking inactive."""
        entry = await self.get_by_service_id(service_id)
        if not entry:
            return False
        entry.is_active = False
        await self._session.flush()
        return True
