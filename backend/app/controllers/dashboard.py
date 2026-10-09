"""
Dashboard controller — thin transport boundary for the summary endpoint.
"""

from ..schemas.dashboard import DashboardSummaryResponse
from ..services.dashboard import DashboardService


class DashboardController:
    """Expose dashboard summary business logic to routes."""

    def __init__(self, service: DashboardService) -> None:
        """Initialise with a DashboardService."""
        self.service = service

    async def get_summary(self) -> DashboardSummaryResponse:
        """Return the aggregate dashboard summary."""
        return await self.service.get_summary()
