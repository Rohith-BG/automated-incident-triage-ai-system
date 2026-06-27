import pytest

from backend.app.controllers.service_catalog import ServiceCatalogController
from backend.app.exceptions import ValidationException
from backend.app.schemas.services import ServiceSummary


class FakeServiceCatalogUseCase:
    def __init__(self) -> None:
        self.received_service_id: str | None = None

    async def list_services(self) -> list[ServiceSummary]:
        return []

    async def get_service(self, service_id: str):
        self.received_service_id = service_id
        return None

    async def get_dependencies(self, service_id: str):
        self.received_service_id = service_id
        return None

    async def get_blast_radius(self, target_id: str):
        self.received_service_id = target_id
        return None


@pytest.mark.asyncio
async def test_controller_normalizes_service_identifier_before_service_call() -> None:
    service_catalog = FakeServiceCatalogUseCase()
    controller = ServiceCatalogController(service_catalog=service_catalog)

    await controller.get_service("  cart-service  ")

    assert service_catalog.received_service_id == "cart-service"


@pytest.mark.asyncio
async def test_controller_rejects_invalid_service_identifier() -> None:
    service_catalog = FakeServiceCatalogUseCase()
    controller = ServiceCatalogController(service_catalog=service_catalog)

    with pytest.raises(ValidationException) as exc_info:
        await controller.get_dependencies("   ")

    exc = exc_info.value
    assert exc.message == "Invalid service identifier."
    assert exc.context["service_id"] == "   "
    assert exc.context["validation_errors"]
    assert service_catalog.received_service_id is None
