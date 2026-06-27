from fastapi import APIRouter, Depends

from ..controllers.service_catalog import ServiceCatalogController
from ..schemas.services import (
    BlastRadiusResponse,
    ServiceDependenciesResponse,
    ServiceDetail,
    ServiceSummary,
)

router = APIRouter(tags=["services"])


def get_service_catalog_controller() -> ServiceCatalogController:
    return ServiceCatalogController()


@router.get("/services", response_model=list[ServiceSummary])
async def list_services(
    controller: ServiceCatalogController = Depends(get_service_catalog_controller),
) -> list[ServiceSummary]:
    return await controller.list_services()


@router.get("/services/{service_id}", response_model=ServiceDetail)
async def get_service(
    service_id: str,
    controller: ServiceCatalogController = Depends(get_service_catalog_controller),
) -> ServiceDetail:
    return await controller.get_service(service_id)


@router.get(
    "/services/{service_id}/dependencies",
    response_model=ServiceDependenciesResponse,
)
async def get_dependencies(
    service_id: str,
    controller: ServiceCatalogController = Depends(get_service_catalog_controller),
) -> ServiceDependenciesResponse:
    return await controller.get_dependencies(service_id)


@router.get(
    "/services/{service_id}/blast-radius",
    response_model=BlastRadiusResponse,
)
async def get_blast_radius(
    service_id: str,
    controller: ServiceCatalogController = Depends(get_service_catalog_controller),
) -> BlastRadiusResponse:
    return await controller.get_blast_radius(service_id)
