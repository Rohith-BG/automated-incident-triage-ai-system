import pytest

from backend.app.services.service_catalog import (
    ServiceCatalogService,
)
from backend.app.exceptions import NotFoundException


@pytest.mark.asyncio
async def test_list_services_includes_team_oncall() -> None:
    service_catalog = ServiceCatalogService()

    services = await service_catalog.list_services()

    frontend = next(service for service in services if service.id == "frontend")
    assert len(services) == 11
    assert frontend.owner_team == "platform-team"
    assert frontend.oncall_slack == "#platform-oncall"


@pytest.mark.asyncio
async def test_get_dependencies_classifies_database_dependency() -> None:
    service_catalog = ServiceCatalogService()

    response = await service_catalog.get_dependencies("cart-service")

    assert response.service_id == "cart-service"
    assert response.dependencies[0].id == "redis-cart"
    assert response.dependencies[0].dependency_type == "database"


@pytest.mark.asyncio
async def test_get_dependencies_classifies_external_api_dependency() -> None:
    service_catalog = ServiceCatalogService()

    response = await service_catalog.get_dependencies("payment-service")

    assert response.dependencies[0].id == "stripe-api"
    assert response.dependencies[0].dependency_type == "external_api"


@pytest.mark.asyncio
async def test_blast_radius_walks_reverse_dependencies() -> None:
    service_catalog = ServiceCatalogService()

    response = await service_catalog.get_blast_radius("redis-cart")
    affected_ids = {service.id for service in response.affected_services}

    assert response.target_id == "redis-cart"
    assert response.direct_dependents == ["cart-service"]
    assert affected_ids == {
        "cart-service",
        "checkout-service",
        "frontend",
        "load-generator",
    }
    assert response.impact_count == 4


@pytest.mark.asyncio
async def test_unknown_service_raises_not_found() -> None:
    service_catalog = ServiceCatalogService()

    with pytest.raises(NotFoundException) as exc_info:
        await service_catalog.get_service("missing-service")

    exc = exc_info.value
    log_payload = exc.to_log_payload()
    assert exc.status_code == 404
    assert exc.message == "Unknown service: missing-service"
    assert exc.context == {"service_id": "missing-service"}
    assert log_payload["exception_type"] == "NotFoundException"
    assert log_payload["status_code"] == 404
    assert log_payload["stack_trace"]
