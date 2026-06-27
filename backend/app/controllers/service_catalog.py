from pydantic import ValidationError

from ..exceptions import ValidationException
from ..schemas.service_requests import ServiceIdentifierRequest
from ..schemas.services import (
    BlastRadiusResponse,
    ServiceDependenciesResponse,
    ServiceDetail,
    ServiceSummary,
)
from ..services.service_catalog import ServiceCatalogService


class ServiceCatalogController:
    def __init__(self, service_catalog: ServiceCatalogService | None = None) -> None:
        self.service_catalog = service_catalog or ServiceCatalogService()

    async def list_services(self) -> list[ServiceSummary]:
        return await self.service_catalog.list_services()

    async def get_service(self, service_id: str) -> ServiceDetail:
        request = self._build_service_identifier_request(service_id)
        return await self.service_catalog.get_service(request.service_id)

    async def get_dependencies(self, service_id: str) -> ServiceDependenciesResponse:
        request = self._build_service_identifier_request(service_id)
        return await self.service_catalog.get_dependencies(request.service_id)

    async def get_blast_radius(self, service_id: str) -> BlastRadiusResponse:
        request = self._build_service_identifier_request(service_id)
        return await self.service_catalog.get_blast_radius(request.service_id)

    def _build_service_identifier_request(
        self,
        service_id: str,
    ) -> ServiceIdentifierRequest:
        try:
            return ServiceIdentifierRequest(service_id=service_id)
        except ValidationError as exc:
            raise ValidationException(
                "Invalid service identifier.",
                log_message="Service identifier request validation failed.",
                context={
                    "service_id": service_id,
                    "validation_errors": exc.errors(),
                },
                cause=exc,
            ) from exc
