"""
Database-backed incident knowledge provider.
"""

import logging
from typing import Any, Optional
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.repositories.incident_knowledge import IncidentKnowledgeRepository
from backend.app.repositories.incident_resolution import IncidentResolutionRepository
from backend.app.repositories.incident import IncidentRepository

logger = logging.getLogger(__name__)


class DBIncidentKnowledgeProvider:
    """Production provider querying Postgres/SQLite database directly for knowledge."""

    def __init__(self, session_maker: async_sessionmaker) -> None:
        """Initialise with database session maker."""
        self._session_maker = session_maker

    async def search_incident_knowledge(
        self,
        service: str,
        error_type: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search database for matching incident knowledge entries."""
        logger.info("Database query for matching knowledge entries on service %s", service)
        async with self._session_maker() as session:
            repo = IncidentKnowledgeRepository(session)
            matches = await repo.find_matching(
                service_id=service,
                error_type=error_type,
                query_str=query,
                limit=limit,
            )
            return [m.to_dict() for m in matches]

    async def get_incident_knowledge(
        self,
        incident_knowledge_id: str,
    ) -> Optional[dict[str, Any]]:
        """Fetch details of a specific incident knowledge entry."""
        logger.info("Database query for incident knowledge entry ID %s", incident_knowledge_id)
        async with self._session_maker() as session:
            repo = IncidentKnowledgeRepository(session)
            ik = await repo.get_by_id(incident_knowledge_id)
            return ik.to_dict() if ik else None

    async def get_past_resolutions(
        self,
        service: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Fetch past resolutions for similar incidents on service from DB."""
        logger.info("Database query for past resolutions on service %s", service)
        from sqlalchemy import select
        from backend.app.models.incident_resolution import IncidentResolution
        from backend.app.models.incident import Incident

        results = []
        async with self._session_maker() as session:
            # Query resolutions associated with incidents of this service
            stmt = (
                select(IncidentResolution)
                .join(Incident, Incident.id == IncidentResolution.incident_id)
                .where(Incident.service_id == service)
            )
            stmt = stmt.order_by(IncidentResolution.created_at.desc()).limit(limit)
            res = await session.execute(stmt)
            resolutions = res.scalars().all()
            for r in resolutions:
                results.append(r.to_dict())
        return results

    async def get_similar_incidents(
        self,
        service: str,
        error_pattern: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Fetch historical incidents for service from database."""
        logger.info("Database query for historical incidents on service %s", service)
        from sqlalchemy import select
        from backend.app.models.incident import Incident
        from backend.app.enums import IncidentStatus

        results = []
        async with self._session_maker() as session:
            # Find completed incidents
            stmt = (
                select(Incident)
                .where(Incident.service_id == service)
                .where(Incident.status == IncidentStatus.COMPLETED.value)
                .order_by(Incident.created_at.desc())
            )
            res = await session.execute(stmt)
            incidents = res.scalars().all()
            for inc in incidents:
                # Simple pattern filtering if pattern is given
                if error_pattern and inc.report:
                    rc = inc.report.root_cause.lower()
                    es = inc.report.observability_analysis.lower()
                    if error_pattern.lower() not in rc and error_pattern.lower() not in es:
                        continue
                results.append(inc.to_dict())
                if len(results) >= limit:
                    break
        return results
