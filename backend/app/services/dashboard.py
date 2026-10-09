"""
Dashboard service — business logic for the operations summary.

Computes the aggregate incident and service-health figures from
the incident repository and the service catalog. This is the
single backend source of truth for the board's metric cards;
the frontend renders only what this service returns.
"""

import logging
from datetime import datetime, time, timezone

from ..repositories.incident import IncidentRepository
from ..schemas.dashboard import (
    DashboardSummaryResponse,
    IncidentSummaryMetrics,
    ServiceHealthMetrics,
)
from ..services.service_catalog import ServiceCatalogService

logger = logging.getLogger(__name__)

CRITICAL_ACTIVE_THRESHOLD = 2


class DashboardService:
    """Business logic that produces the operations summary."""

    def __init__(
        self,
        incident_repository: IncidentRepository,
        service_catalog: ServiceCatalogService | None = None,
    ) -> None:
        """Initialise with an incident repository and service catalog.

        Args:
            incident_repository: Injected via FastAPI Depends chain.
            service_catalog: Injected; defaults to the catalog-file service.
        """
        self._incident_repo = incident_repository
        self._service_catalog = service_catalog or ServiceCatalogService()

    async def get_summary(self) -> DashboardSummaryResponse:
        """Return the aggregate dashboard summary.

        Computes active/resolved-today incident counts and classifies
        each known service as healthy, degraded, or critical based on
        its number of active incidents.

        Returns:
            A DashboardSummaryResponse with incident and service-health metrics.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        start_of_today = datetime.combine(now.date(), time.min)

        active_count, resolved_today, active_by_service = await self._gather_counts(
            start_of_today
        )

        service_ids = [
            service.id
            for service in await self._service_catalog.list_services()
        ]

        healthy = 0
        degraded = 0
        critical = 0
        for service_id in service_ids:
            n = active_by_service.get(service_id, 0)
            if n >= CRITICAL_ACTIVE_THRESHOLD:
                critical += 1
            elif n == 1:
                degraded += 1
            else:
                healthy += 1

        return DashboardSummaryResponse(
            incident_summary=IncidentSummaryMetrics(
                active=active_count,
                resolved_today=resolved_today,
            ),
            service_health=ServiceHealthMetrics(
                healthy=healthy,
                degraded=degraded,
                critical=critical,
                total=len(service_ids),
            ),
        )

    async def _gather_counts(
        self, start_of_today: datetime
    ) -> tuple[int, int, dict[str, int]]:
        """Fetch the three incident aggregates concurrently."""
        import asyncio

        active_count, resolved_today, active_by_service = await asyncio.gather(
            self._incident_repo.count_active(),
            self._incident_repo.count_resolved_since(start_of_today),
            self._incident_repo.count_active_by_service(),
        )
        return active_count, resolved_today, active_by_service
