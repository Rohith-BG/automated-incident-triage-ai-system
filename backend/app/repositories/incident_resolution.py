"""
Incident resolution repository — database access for post-incident resolutions.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.incident_resolution import IncidentResolution

logger = logging.getLogger(__name__)


class IncidentResolutionRepository:
    """Data-access layer for IncidentResolution."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with an async database session."""
        self._session = session

    async def create(
        self,
        *,
        incident_id: str,
        resolved_by: str,
        what_was_root_cause: str,
        what_fixed_it: str,
        time_to_resolve_min: int,
        should_update_incident_knowledge: bool = False,
        incident_knowledge_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> IncidentResolution:
        """Create and persist a new incident resolution."""
        resolution = IncidentResolution(
            incident_id=incident_id,
            resolved_by=resolved_by,
            what_was_root_cause=what_was_root_cause,
            what_fixed_it=what_fixed_it,
            time_to_resolve_min=time_to_resolve_min,
            should_update_incident_knowledge=should_update_incident_knowledge,
            incident_knowledge_id=incident_knowledge_id,
            notes=notes,
        )
        self._session.add(resolution)
        await self._session.flush()
        await self._session.refresh(resolution)
        logger.info(
            "Created IncidentResolution %s for incident %s (resolved by %s)",
            resolution.id,
            incident_id,
            resolved_by,
        )
        return resolution

    async def get_by_incident(self, incident_id: str) -> Optional[IncidentResolution]:
        """Fetch resolution for a given incident."""
        stmt = select(IncidentResolution).where(IncidentResolution.incident_id == incident_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
