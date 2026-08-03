"""
Service Topology Onboarding REST API routes.

Provides endpoints for auto-discovering service topologies,
registering services, and querying onboarding status.
"""

from fastapi import APIRouter, Depends, status

from backend.app.controllers.onboarding import OnboardingController
from backend.app.dependencies import (
    get_current_user,
    get_onboarding_controller,
    require_role,
)
from backend.app.enums import UserRole
from backend.app.models.user import User
from backend.app.schemas.onboarding import (
    DiscoverTopologyRequest,
    OnboardingResultResponse,
    OnboardingStatusResponse,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post(
    "/discover",
    response_model=OnboardingResultResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Discover service topology and generate Knowledge Graph proposal",
)
async def discover_topology(
    payload: DiscoverTopologyRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.SRE)),
    controller: OnboardingController = Depends(get_onboarding_controller),
) -> OnboardingResultResponse:
    """Discover service topology, upsert services in registry, and generate pending KG proposal for human review."""
    return await controller.discover_topology(payload)


@router.get(
    "/status",
    response_model=OnboardingStatusResponse,
    summary="Get platform topology onboarding status",
)
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
    controller: OnboardingController = Depends(get_onboarding_controller),
) -> OnboardingStatusResponse:
    """Return high-level onboarding status metrics across registered services and pending proposals."""
    return await controller.get_status()
