"""
Incident knowledge REST API routes.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from ..controllers.incident_knowledge import IncidentKnowledgeController
from ..dependencies import get_incident_knowledge_controller, require_role
from ..enums import UserRole
from ..models.user import User
from ..schemas.incident_knowledge import (
    CreateIncidentKnowledgeRequest,
    IncidentKnowledgeListResponse,
    IncidentKnowledgeResponse,
    UpdateIncidentKnowledgeRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/incident-knowledge", tags=["incident-knowledge"])


@router.post(
    "",
    response_model=IncidentKnowledgeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SRE incident knowledge entry (Admin only)",
)
async def create_knowledge(
    payload: CreateIncidentKnowledgeRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    controller: IncidentKnowledgeController = Depends(get_incident_knowledge_controller),
) -> IncidentKnowledgeResponse:
    """Create a new SRE runbook / incident knowledge entry."""
    return await controller.create_knowledge(created_by=current_user.email, payload=payload)


@router.get(
    "",
    response_model=IncidentKnowledgeListResponse,
    summary="List SRE incident knowledge entries",
)
async def list_knowledge(
    limit: int = Query(20, ge=1, le=100, description="Max items per page"),
    cursor: Optional[str] = Query(None, description="Opaque cursor for pagination"),
    service_id: Optional[str] = Query(None, description="Filter by service ID"),
    controller: IncidentKnowledgeController = Depends(get_incident_knowledge_controller),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.SRE, UserRole.TEAM_MEMBER)),
) -> IncidentKnowledgeListResponse:
    """Fetch paginated SRE incident knowledge entries."""
    return await controller.list_knowledge(limit=limit, cursor=cursor, service_id=service_id)


@router.get(
    "/{ik_id}",
    response_model=IncidentKnowledgeResponse,
    summary="Get SRE incident knowledge detail",
)
async def get_knowledge(
    ik_id: str,
    controller: IncidentKnowledgeController = Depends(get_incident_knowledge_controller),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.SRE, UserRole.TEAM_MEMBER)),
) -> IncidentKnowledgeResponse:
    """Fetch detail of a single knowledge entry."""
    return await controller.get_knowledge(ik_id=ik_id)


@router.put(
    "/{ik_id}",
    response_model=IncidentKnowledgeResponse,
    summary="Update SRE incident knowledge entry (Admin only)",
)
async def update_knowledge(
    ik_id: str,
    payload: UpdateIncidentKnowledgeRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    controller: IncidentKnowledgeController = Depends(get_incident_knowledge_controller),
) -> IncidentKnowledgeResponse:
    """Partially update an existing SRE knowledge entry."""
    return await controller.update_knowledge(ik_id=ik_id, payload=payload)


@router.delete(
    "/{ik_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete SRE incident knowledge entry (Admin only)",
)
async def delete_knowledge(
    ik_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    controller: IncidentKnowledgeController = Depends(get_incident_knowledge_controller),
) -> None:
    """Delete an SRE knowledge entry."""
    await controller.delete_knowledge(ik_id=ik_id)
