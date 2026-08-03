"""
Onboarding controller.

Handles transport concerns for service topology discovery.
Delegates business logic strictly to OnboardingService.
"""

import logging
from backend.app.schemas.onboarding import (
    DiscoverTopologyRequest,
    OnboardingResultResponse,
    OnboardingStatusResponse,
)
from backend.app.services.onboarding import OnboardingService

logger = logging.getLogger(__name__)


class OnboardingController:
    """Controller for topology onboarding."""

    def __init__(self, service: OnboardingService) -> None:
        """Initialise with injected service."""
        self._service = service

    async def discover_topology(
        self, payload: DiscoverTopologyRequest
    ) -> OnboardingResultResponse:
        """Trigger topology discovery and proposal generation."""
        logger.info(
            "Executing topology discovery for architecture=%s source=%s",
            payload.architecture_type,
            payload.source_type,
        )
        return await self._service.discover_and_onboard(payload)

    async def get_status(self) -> OnboardingStatusResponse:
        """Get overall platform onboarding status."""
        return await self._service.get_onboarding_status()
