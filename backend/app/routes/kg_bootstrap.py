"""
FastAPI route handlers for the KG bootstrap agent trigger.
"""

from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status

from ..dependencies import (
    get_kg_bootstrap_service,
    get_current_user,
    require_role,
)
from ..enums import UserRole
from ..exceptions import ForbiddenException
from ..models.user import User
from ..schemas.kg_bootstrap import (
    KgBootstrapRunRequest,
    KgBootstrapRunResponse,
    KgBootstrapStatusResponse,
    KgStagingSnapshotResponse,
)
from ..services.kg_bootstrap import KgBootstrapService

router = APIRouter(prefix="/kg-bootstrap", tags=["KG Bootstrap"])


@router.post(
    "/run",
    response_model=KgBootstrapRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_bootstrap(
    background_tasks: BackgroundTasks,
    payload: Optional[KgBootstrapRunRequest] = None,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: KgBootstrapService = Depends(get_kg_bootstrap_service),
) -> Any:
    """Trigger the KG bootstrap agent (admin only).

    Runs as a background task; a notification is created when the
    staged graph is ready for review.
    """
    if not service.is_bootstrap_enabled:
        raise ForbiddenException(
            "KG bootstrap is disabled in this environment "
            "(KG_BOOTSTRAP_ENABLED=false)."
        )
    req = payload or KgBootstrapRunRequest()
    background_tasks.add_task(
        service.run_bootstrap,
        user_email=current_user.email,
        source=req.source,
        org=req.org,
        repo=req.repo,
        architecture_type=req.architecture_type,
    )
    return KgBootstrapRunResponse(status="started")


@router.get(
    "/status",
    response_model=KgBootstrapStatusResponse,
)
async def bootstrap_status(
    current_user: User = Depends(get_current_user),
    service: KgBootstrapService = Depends(get_kg_bootstrap_service),
) -> Any:
    """Return KG bootstrap status to drive the 'Build KG' CTA."""
    return await service.get_status()


@router.get(
    "/staging",
    response_model=KgStagingSnapshotResponse,
)
async def staging_snapshot(
    current_user: User = Depends(get_current_user),
    service: KgBootstrapService = Depends(get_kg_bootstrap_service),
) -> Any:
    """Return the currently staged graph for visualization."""
    snapshot = await service.get_staging_snapshot()
    return KgStagingSnapshotResponse(**snapshot)


@router.get(
    "/active",
    response_model=KgStagingSnapshotResponse,
)
async def active_snapshot(
    current_user: User = Depends(get_current_user),
    service: KgBootstrapService = Depends(get_kg_bootstrap_service),
) -> Any:
    """Return the currently active graph for visualization."""
    snapshot = await service.get_active_snapshot()
    return KgStagingSnapshotResponse(**snapshot)

