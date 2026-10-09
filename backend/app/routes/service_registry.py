"""
FastAPI route handlers for Service Registry management.
"""

from typing import Any
from fastapi import APIRouter, Depends, status

from ..dependencies import (
    get_current_user,
    get_kg_proposal_service,
    get_service_registry_service,
    require_role,
)
from ..enums import UserRole
from ..models.user import User
from ..schemas.service_registry import (
    ServiceRegistryCreate,
    ServiceRegistryResponse,
    ServiceRegistryUpdate,
)
from ..services.service_registry import KGProposalService, ServiceRegistryService

router = APIRouter(prefix="/service-registry", tags=["Service Registry"])


@router.post(
    "",
    response_model=ServiceRegistryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_service(
    payload: ServiceRegistryCreate,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: ServiceRegistryService = Depends(get_service_registry_service),
) -> Any:
    """Register or update a service entry in the registry (Admin only)."""
    return await service.register_service(**payload.model_dump())


@router.get("", response_model=list[ServiceRegistryResponse])
async def list_services(
    active_only: bool = True,
    service: ServiceRegistryService = Depends(get_service_registry_service),
    current_user: User = Depends(get_current_user),
) -> Any:
    """List registered services."""
    return await service.list_services(active_only=active_only)


@router.get("/{service_id}", response_model=ServiceRegistryResponse)
async def get_service(
    service_id: str,
    service: ServiceRegistryService = Depends(get_service_registry_service),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get service details by service_id."""
    return await service.get_service(service_id)


@router.patch(
    "/{service_id}",
    response_model=ServiceRegistryResponse,
)
async def update_service(
    service_id: str,
    payload: ServiceRegistryUpdate,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: ServiceRegistryService = Depends(get_service_registry_service),
) -> Any:
    """Update service registry entry (Admin only)."""
    return await service.update_service(service_id, **payload.model_dump(exclude_unset=True))


@router.delete(
    "/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_service(
    service_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: ServiceRegistryService = Depends(get_service_registry_service),
) -> None:
    """Deactivate a service from the registry (Admin only)."""
    await service.delete_service(service_id)


@router.post(
    "/sync-from-kg",
    status_code=status.HTTP_200_OK,
    summary="Sync services from the active Knowledge Graph into the registry",
)
async def sync_from_kg(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    proposal_service: "KGProposalService" = Depends(get_kg_proposal_service),
) -> dict[str, Any]:
    """Read all services from the active KG and upsert into the registry.

    Useful when a KG was approved before the automatic sync was added,
    or to refresh registry metadata from the graph.
    """
    synced = await proposal_service.sync_services_from_kg()
    return {"synced": synced, "message": f"Synced {synced} services from KG"}
