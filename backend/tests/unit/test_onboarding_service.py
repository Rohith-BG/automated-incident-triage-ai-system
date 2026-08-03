"""
Unit tests for OnboardingService & scanner strategies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.app.schemas.onboarding import (
    DiscoveredServiceInput,
    DiscoverTopologyRequest,
)
from backend.app.services.onboarding import (
    InlineScanner,
    OnboardingService,
    ScannerFactory,
    ServicesJsonScanner,
)


@pytest.mark.asyncio
async def test_scanner_factory():
    """ScannerFactory returns correct scanner strategy."""
    inline_scanner = ScannerFactory.get_scanner("inline")
    assert isinstance(inline_scanner, InlineScanner)

    json_scanner = ScannerFactory.get_scanner("services_json")
    assert isinstance(json_scanner, ServicesJsonScanner)

    with pytest.raises(ValueError, match="Unsupported discovery source_type"):
        ScannerFactory.get_scanner("invalid_source")


@pytest.mark.asyncio
async def test_inline_scanner():
    """InlineScanner returns provided services list."""
    scanner = InlineScanner()
    req = DiscoverTopologyRequest(
        architecture_type="microservice",
        source_type="inline",
        owner_team_id="team-a",
        services=[
            DiscoveredServiceInput(
                service_id="svc-1",
                repo="org/svc-1",
                architecture_type="microservice",
                owner_team_id="team-a",
                dependencies=["svc-2"],
            )
        ],
    )
    result = await scanner.scan(req)
    assert len(result) == 1
    assert result[0].service_id == "svc-1"


@pytest.mark.asyncio
async def test_onboarding_service_discover():
    """OnboardingService registers services and generates a pending proposal."""
    registry_repo = AsyncMock()
    proposal_repo = AsyncMock()

    # Mock get_by_service_id returning None (new service)
    registry_repo.get_by_service_id.return_value = None

    proposal_mock = MagicMock()
    proposal_mock.id = "prop-123"
    proposal_repo.create.return_value = proposal_mock

    service = OnboardingService(
        service_registry_repo=registry_repo,
        kg_proposal_repo=proposal_repo,
    )

    req = DiscoverTopologyRequest(
        architecture_type="microservice",
        source_type="inline",
        owner_team_id="platform-team",
        services=[
            DiscoveredServiceInput(
                service_id="payment-service",
                repo="demo/payment",
                architecture_type="microservice",
                owner_team_id="payments-team",
                dependencies=["stripe-api"],
            )
        ],
    )

    res = await service.discover_and_onboard(req)

    assert res.discovered_count == 1
    assert res.registered_count == 1
    assert res.proposal_id == "prop-123"
    registry_repo.create.assert_called_once()
    proposal_repo.create.assert_called_once()
