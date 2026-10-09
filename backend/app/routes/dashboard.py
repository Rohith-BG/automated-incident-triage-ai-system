"""
Dashboard summary routes.

Provides the aggregate `GET /dashboard/summary` readout used by the
operations board's metric cards. All figures are computed server-side;
this route holds no business logic.
"""

from fastapi import APIRouter, Depends

from ..controllers.dashboard import DashboardController
from ..dependencies import get_dashboard_controller
from ..schemas.dashboard import DashboardSummaryResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    controller: DashboardController = Depends(get_dashboard_controller),
) -> DashboardSummaryResponse:
    """Return aggregate incident and service-health metrics for the board."""
    return await controller.get_summary()
